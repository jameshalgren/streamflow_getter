"""Benchmark reading NWM operational channel_rt streamflow for a few reaches.

Compares native NetCDF on S3 (whole-file download, byte-range reads) with the
CIROH Kerchunk references (as published, pointing at GCS; rewritten to point
at S3; and a direct path that fetches only the streamflow chunk per file).

    uv run --group bench python benchmarks/kerchunk_vs_native.py --help

Timings depend on the network and machine; record both with the results.
"""

import argparse
import base64
import io
import json
import os
import platform
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import fsspec.implementations.http as fs_http
import numcodecs
import numpy as np
import pandas as pd
import s3fs
import xarray as xr
from fsspec.implementations.reference import ReferenceFileSystem
from zarr.storage import FsspecStore

NATIVE = "noaa-nwm-pds"
REFS = "ciroh-nwm-zarr-copy/national-water-model"
GCS_HTTPS = "https://storage.googleapis.com/national-water-model/"

# Alabama gaged reaches (USGS gage -> NWM feature_id), from the retrospective store.
REACHES = {
    "02413300": 15811667,  # Little Tallapoosa
    "02424000": 21661814,  # Cahaba
    "02462000": 18229157,  # Sipsey Fork
    "02465000": 18229923,  # Black Warrior
    "02467000": 18540822,  # Tombigbee
    "02428400": 18239649,  # Alabama River
}

# --- byte counting -----------------------------------------------------------
# Every remote read in the paths below goes through one of these methods.

_lock = threading.Lock()
_bytes = {"n": 0, "requests": 0}


def _count(n: int) -> None:
    with _lock:
        _bytes["n"] += n
        _bytes["requests"] += 1


def _wrap_async(cls, name):
    orig = getattr(cls, name)

    async def wrapper(self, *args, **kwargs):
        out = await orig(self, *args, **kwargs)
        _count(len(out))
        return out

    setattr(cls, name, wrapper)


def _wrap_sync(cls, name):
    orig = getattr(cls, name)

    def wrapper(self, *args, **kwargs):
        out = orig(self, *args, **kwargs)
        _count(len(out))
        return out

    setattr(cls, name, wrapper)


_wrap_async(s3fs.S3FileSystem, "_cat_file")
_wrap_async(fs_http.HTTPFileSystem, "_cat_file")
_wrap_sync(s3fs.core.S3File, "_fetch_range")


# --- file lists ----------------------------------------------------------------


def file_names(date: str, product: str, cycle: str, domain: str) -> list[str]:
    fs = s3fs.S3FileSystem(anon=True)
    names = [
        p.rsplit("/", 1)[-1]
        for p in fs.ls(f"{NATIVE}/nwm.{date}/{product}/")
        if f".t{cycle}z." in p and ".channel_rt" in p and f".{domain}.nc" in p
    ]
    return sorted(names)


# --- read paths: each returns {valid_time: values aligned with ids} ------------


def _select(ds: xr.Dataset, ids: list[int]) -> tuple[np.datetime64, np.ndarray]:
    return ds.time.values[0], ds.streamflow.sel(feature_id=ids).values.astype(float)


def native_full(date, product, names, ids, workers):
    fs = s3fs.S3FileSystem(anon=True, skip_instance_cache=True)

    def one(name):
        raw = fs.cat_file(f"{NATIVE}/nwm.{date}/{product}/{name}")
        with xr.open_dataset(io.BytesIO(raw), engine="h5netcdf") as ds:
            return _select(ds, ids)

    with ThreadPoolExecutor(workers) as pool:
        return dict(pool.map(one, names))


def native_range(date, product, names, ids, workers, block_size=2**20):
    fs = s3fs.S3FileSystem(anon=True, skip_instance_cache=True)

    def one(name):
        path = f"{NATIVE}/nwm.{date}/{product}/{name}"
        with fs.open(path, block_size=block_size, cache_type="readahead") as f:
            with xr.open_dataset(f, engine="h5netcdf") as ds:
                return _select(ds, ids)

    with ThreadPoolExecutor(workers) as pool:
        return dict(pool.map(one, names))


def _load_refs(date, product, names, workers):
    fs = s3fs.S3FileSystem(anon=True, skip_instance_cache=True)
    paths = [f"{REFS}/nwm.{date}/{product}/{n}.json" for n in names]
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(lambda p: json.loads(fs.cat_file(p)), paths))


def _to_s3(ref: dict) -> dict:
    return json.loads(json.dumps(ref).replace(GCS_HTTPS, f"s3://{NATIVE}/"))


def _open_ref(ref, protocol, options):
    rfs = ReferenceFileSystem(
        ref,
        remote_protocol=protocol,
        remote_options={**options, "asynchronous": True},
        asynchronous=True,
        skip_instance_cache=True,
    )
    store = FsspecStore(rfs, read_only=True)
    return xr.open_dataset(store, engine="zarr", chunks=None, consolidated=False, zarr_format=2)


def _kerchunk_xarray(date, product, names, ids, workers, to_s3):
    refs = _load_refs(date, product, names, workers)
    protocol, options = ("s3", {"anon": True}) if to_s3 else ("https", {})

    def one(ref):
        ref = _to_s3(ref) if to_s3 else ref
        with _open_ref(ref, protocol, options) as ds:
            return _select(ds, ids)

    with ThreadPoolExecutor(workers) as pool:
        return dict(pool.map(one, refs))


def kerchunk_gcs(date, product, names, ids, workers):
    return _kerchunk_xarray(date, product, names, ids, workers, to_s3=False)


def kerchunk_s3(date, product, names, ids, workers):
    return _kerchunk_xarray(date, product, names, ids, workers, to_s3=True)


def _decode(raw: bytes, zarray: dict) -> np.ndarray:
    for spec in reversed(zarray["filters"] or []):
        raw = numcodecs.get_codec(spec).decode(raw)
    return np.frombuffer(raw, dtype=zarray["dtype"])


def _inline(value) -> bytes:
    return base64.b64decode(value[7:]) if value.startswith("base64:") else value.encode()


def kerchunk_direct(date, product, names, ids, workers):
    """Fetch only the streamflow chunk per file; read feature_id once."""
    refs = [_to_s3(r)["refs"] for r in _load_refs(date, product, names, workers)]
    fs = s3fs.S3FileSystem(anon=True, skip_instance_cache=True)

    def fetch(entry):
        url, offset, length = entry
        return fs.cat_file(url, start=offset, end=offset + length)

    first = refs[0]
    fid_meta = json.loads(first["feature_id/.zarray"])
    if any(r["feature_id/0"][1:] != first["feature_id/0"][1:] for r in refs):
        raise ValueError("feature_id layout differs across files; read it per file")
    feature_id = _decode(fetch(first["feature_id/0"]), fid_meta)
    pos = pd.Index(feature_id).get_indexer(ids)
    if (pos < 0).any():
        raise ValueError(f"feature_id not found: {np.array(ids)[pos < 0].tolist()}")

    sf_meta = json.loads(first["streamflow/.zarray"])
    sf_attrs = json.loads(first["streamflow/.zattrs"])
    t_meta = json.loads(first["time/.zarray"])

    def one(r):
        raw = _decode(fetch(r["streamflow/0"]), sf_meta)[pos]
        vals = np.where(raw == sf_meta["fill_value"], np.nan, raw * sf_attrs["scale_factor"])
        minutes = _decode(_inline(r["time/0"]), t_meta)[0]
        return np.datetime64(int(minutes), "m").astype("datetime64[ns]"), vals

    with ThreadPoolExecutor(workers) as pool:
        return dict(pool.map(one, refs))


def machine() -> str:
    """CPU, cores, memory and OS, e.g. 'Apple M4 Max, 16 cores, 64 GB, macOS 26.7.1'."""
    cpu, mem_gb = platform.processor() or platform.machine(), None
    if platform.system() == "Darwin":
        def sysctl(key):
            return subprocess.run(["sysctl", "-n", key], capture_output=True, text=True).stdout.strip()
        cpu, mem_gb = sysctl("machdep.cpu.brand_string") or cpu, int(sysctl("hw.memsize")) / 2**30
        system = f"macOS {platform.mac_ver()[0]}"
    else:
        if hasattr(os, "sysconf"):
            mem_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
        system = f"{platform.system()} {platform.release()}"
    mem = f", {mem_gb:.0f} GB" if mem_gb else ""
    return f"{cpu}, {os.cpu_count()} cores{mem}, {system}"


METHODS = {
    "native_full": native_full,
    "native_range": native_range,
    "kerchunk_gcs": kerchunk_gcs,
    "kerchunk_s3": kerchunk_s3,
    "kerchunk_direct": kerchunk_direct,
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--date", default="20260419")
    p.add_argument("--product", default="short_range")
    p.add_argument("--cycle", default="00")
    p.add_argument("--domain", default="conus")
    p.add_argument("--max-files", type=int, help="use only the first N files")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--methods", nargs="+", default=list(METHODS), choices=list(METHODS))
    p.add_argument("--network", default="unspecified",
                   help='connection used, e.g. "Wi-Fi 802.11ax" or "1000 Mbps LAN"')
    p.add_argument("--out", help="append result rows to this CSV")
    args = p.parse_args(argv)

    names = file_names(args.date, args.product, args.cycle, args.domain)[: args.max_files]
    ids = list(REACHES.values())
    print(f"{args.product} {args.date} t{args.cycle}z: {len(names)} files, "
          f"{len(ids)} reaches, {args.workers} workers")

    host = machine()
    rows, reference = [], None
    for rep in range(args.repeat):
        for method in args.methods:
            _bytes.update(n=0, requests=0)
            t = time.perf_counter()
            result = METHODS[method](args.date, args.product, names, ids, args.workers)
            seconds = time.perf_counter() - t
            frame = pd.DataFrame(result, index=ids).T.sort_index()
            if reference is None:
                reference = frame
            same = frame.shape == reference.shape and np.allclose(
                frame.values, reference.values, equal_nan=True
            )
            rows.append({
                "method": method, "repeat": rep, "product": args.product,
                "date": args.date, "cycle": args.cycle, "files": len(names),
                "reaches": len(ids), "workers": args.workers,
                "seconds": round(seconds, 2), "mb_read": round(_bytes["n"] / 1e6, 1),
                "requests": _bytes["requests"], "matches_first": same,
                "machine": host, "network": args.network,
            })
            print(f"  {method:16s} {seconds:7.2f} s  {_bytes['n'] / 1e6:8.1f} MB  "
                  f"{_bytes['requests']:5d} req  match={same}")

    if args.out:
        df = pd.DataFrame(rows)
        try:
            df = pd.concat([pd.read_csv(args.out), df])
        except FileNotFoundError:
            pass
        df.to_csv(args.out, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
