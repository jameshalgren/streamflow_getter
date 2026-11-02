"""NWM operational channel_rt values for a few reaches via CIROH Kerchunk references.

Each reference is a JSON file next to one NetCDF file
(s3://ciroh-nwm-zarr-copy/national-water-model/nwm.YYYYMMDD/<dir>/<file>.nc.json)
that maps every chunk to a byte range in the GCS copy of the file.

Why not xarray/zarr: on Windows, zarr's async HTTP reads crash the interpreter
on exit, and zarr refuses a synchronous file system. The variables are 1-D over
feature_id, so we fetch only the chunks that hold the requested reaches through a
synchronous ReferenceFileSystem and decode them with the codecs in the refs.
v3.0 files store each variable as one chunk; v3.1 (from 2026-08-18) splits
streamflow into 3 and feature_id into 6, so nothing here assumes one chunk.
"""

import json
import warnings
from concurrent.futures import ThreadPoolExecutor
from math import log10

import numcodecs
import numpy as np
import pandas as pd
import s3fs
from fsspec.implementations.reference import ReferenceFileSystem

REFS_ROOT = "ciroh-nwm-zarr-copy/national-water-model"


def _meta(refs: dict, key: str) -> dict:
    value = refs[key]
    return json.loads(value) if isinstance(value, str) else value


def load_refs(path: str, fs=None) -> dict:
    """Flat {key: ref} mapping from a version 0 or version 1 reference file."""
    fs = fs or s3fs.S3FileSystem(anon=True)
    ref = json.loads(fs.cat(path))
    return ref.get("refs", ref)


def read_chunks(rfs, refs: dict, name: str, chunk_ids=None) -> dict[int, np.ndarray]:
    """Raw (undecoded) values of a 1-D variable, keyed by chunk index."""
    zarray = _meta(refs, f"{name}/.zarray")
    n, size = zarray["shape"][0], zarray["chunks"][0]
    if chunk_ids is None:
        chunk_ids = range(-(-n // size))
    out = {}
    for i in chunk_ids:
        buf = rfs.cat(f"{name}/{i}")
        if zarray["compressor"]:
            buf = numcodecs.get_codec(zarray["compressor"]).decode(buf)
        for codec in reversed(zarray["filters"] or []):
            buf = numcodecs.get_codec(codec).decode(buf)
        # The last chunk is stored full size; trim the padding past the end.
        out[i] = np.frombuffer(buf, dtype=zarray["dtype"])[: min(size, n - i * size)]
    return out


def attrs(refs: dict, name: str) -> dict:
    out = dict(_meta(refs, f"{name}/.zattrs"))
    out.setdefault("_fill_value", _meta(refs, f"{name}/.zarray")["fill_value"])
    return out


def decode_time(values: np.ndarray, attrs: dict) -> pd.DatetimeIndex:
    """CF time, e.g. 'minutes since 1970-01-01 00:00:00 UTC', to naive UTC timestamps."""
    unit, _, epoch = attrs["units"].partition(" since ")
    unit = {"seconds": "s", "minutes": "min", "hours": "h", "days": "D"}[unit]
    return pd.Timestamp(epoch.removesuffix(" UTC")) + pd.to_timedelta(values, unit=unit)


def decode_values(values: np.ndarray, attrs: dict) -> np.ndarray:
    """Packed ints to physical values; fill, missing and out-of-range values become NaN."""
    scale = attrs.get("scale_factor", 1.0)
    out = values.astype("float64") * scale + attrs.get("add_offset", 0.0)
    bad = {attrs.get("_fill_value"), attrs.get("_FillValue"), attrs.get("missing_value")} - {None}
    mask = np.isin(values, list(bad))
    if "valid_min" in attrs:
        mask |= values < attrs["valid_min"]
    if "valid_max" in attrs:
        mask |= values > attrs["valid_max"]
    out[mask] = np.nan
    if 0 < scale < 1:
        out = out.round(round(-log10(scale)))  # drops float32 scale_factor noise
    return out


class Reader:
    """Reads requested reaches from channel_rt refs, one file per read() call.

    feature_id is read once per chunk layout and reused: every CONUS channel_rt
    file of v3.0 and v3.1 lists the same 2,776,734 reaches in the same order.
    """

    def __init__(self, reach_ids, variable: str = "streamflow", fs=None, remote_protocol: str = "https"):
        self.reach_ids = np.asarray(reach_ids, dtype="int64")
        self.variable = variable
        self.fs = fs or s3fs.S3FileSystem(anon=True)
        self.remote_protocol = remote_protocol
        self._positions = {}  # (n, chunk size) -> positions of reach_ids

    def positions(self, rfs, refs: dict) -> np.ndarray:
        zarray = _meta(refs, "feature_id/.zarray")
        key = (zarray["shape"][0], zarray["chunks"][0])
        if key not in self._positions:
            ids = np.concatenate(list(read_chunks(rfs, refs, "feature_id").values()))
            pos = np.clip(np.searchsorted(ids, self.reach_ids), 0, len(ids) - 1)
            missing = self.reach_ids[ids[pos] != self.reach_ids]
            if len(missing):
                raise ValueError(f"feature_id not in NWM channel_rt: {missing.tolist()}")
            self._positions[key] = pos
        return self._positions[key]

    def read(self, path: str) -> pd.DataFrame:
        refs = load_refs(path, self.fs)
        rfs = ReferenceFileSystem({"version": 1, "refs": refs}, remote_protocol=self.remote_protocol)
        pos = self.positions(rfs, refs)
        size = _meta(refs, f"{self.variable}/.zarray")["chunks"][0]
        chunks = read_chunks(rfs, refs, self.variable, sorted(set(pos // size)))
        raw = np.array([chunks[p // size][p % size] for p in pos])
        time_values = np.concatenate(list(read_chunks(rfs, refs, "time").values()))
        return pd.DataFrame({
            "valid_time": decode_time(time_values, attrs(refs, "time"))[0],
            "feature_id": self.reach_ids,
            self.variable: decode_values(raw, attrs(refs, self.variable)),
            "nwm_version": _meta(refs, ".zattrs").get("NWM_version_number"),
            "ref_path": path,
        })


def read_refs(
    ref_paths: list[str],
    reach_ids: list[int],
    variable: str = "streamflow",
    workers: int = 8,
    fs=None,
) -> pd.DataFrame:
    """Long-format frame: valid_time (UTC), feature_id, <variable>, nwm_version, ref_path.

    Missing reference files are skipped with a warning and listed in
    df.attrs["missing"], so a caller can fall back to the native files.
    """
    if not ref_paths:
        raise ValueError("no reference paths given")
    reader = Reader(reach_ids, variable, fs)
    missing = []

    def run(path):
        try:
            return reader.read(path)
        except FileNotFoundError:
            missing.append(path)
            return None

    # Read one file first so feature_id is resolved before going parallel.
    frames = [run(ref_paths[0])]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        frames += pool.map(run, ref_paths[1:])
    frames = [f for f in frames if f is not None]
    if not frames:
        raise FileNotFoundError(f"none of {len(ref_paths)} reference files found")
    if missing:
        warnings.warn(f"{len(missing)} reference file(s) not found, skipped: {missing[:3]}...")
    df = pd.concat(frames, ignore_index=True)
    df.attrs["missing"] = sorted(missing)
    return df
