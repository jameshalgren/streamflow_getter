import base64
import json

import numcodecs
import numpy as np
import pandas as pd
import pytest
from fsspec.implementations.memory import MemoryFileSystem

from streamflow_getter import nwm_kerchunk

ZLIB = {"id": "zlib", "level": 2}
SHUFFLE = {"id": "shuffle", "elementsize": 4}


def _var(refs, name, values, chunk, dtype, fill, attrs, filters=None):
    """Inline a 1-D variable as base64 chunks, encoded the way the NWM refs are."""
    values = np.asarray(values, dtype=dtype)
    refs[f"{name}/.zarray"] = json.dumps({
        "shape": [len(values)], "chunks": [chunk], "dtype": values.dtype.str,
        "compressor": ZLIB, "filters": filters, "fill_value": fill,
        "order": "C", "zarr_format": 2,
    })
    refs[f"{name}/.zattrs"] = json.dumps(attrs)
    for i in range(-(-len(values) // chunk)):
        part = np.zeros(chunk, dtype=values.dtype)  # last chunk stored full size
        piece = values[i * chunk:(i + 1) * chunk]
        part[: len(piece)] = piece
        buf = part.tobytes()
        for codec in filters or []:
            buf = numcodecs.get_codec(codec).encode(buf)
        buf = numcodecs.get_codec(ZLIB).encode(buf)
        refs[f"{name}/{i}"] = "base64:" + base64.b64encode(bytes(buf)).decode()


def make_ref(fs, path, flow, minutes, version="v3.1", chunk=2):
    refs = {".zgroup": json.dumps({"zarr_format": 2}),
            ".zattrs": json.dumps({"NWM_version_number": version})}
    _var(refs, "feature_id", [10, 20, 30, 40, 50], chunk, "<i8", None, {})
    _var(refs, "streamflow", flow, chunk, "<i4", -999900,
         {"scale_factor": 0.0099999998, "missing_value": -999900, "units": "m3 s-1"},
         filters=[SHUFFLE])
    _var(refs, "time", [minutes], 1, "<i4", None,
         {"units": "minutes since 1970-01-01 00:00:00 UTC"})
    fs.pipe(path, json.dumps({"version": 1, "refs": refs}).encode())
    return path


@pytest.fixture
def fs():
    fs = MemoryFileSystem()
    yield fs
    fs.store.clear()


T0 = int(pd.Timestamp("2026-04-19").timestamp() // 60)


def test_reads_reaches_across_chunks(fs):
    path = make_ref(fs, "/a.json", [100, 2300, -999900, 4012, 5], T0 + 60)
    df = nwm_kerchunk.read_refs([path], [50, 20, 30], fs=fs, workers=1)
    assert list(df.columns) == ["valid_time", "feature_id", "streamflow", "nwm_version", "ref_path"]
    assert df.feature_id.tolist() == [50, 20, 30]
    assert df.streamflow.tolist()[:2] == [0.05, 23.0]  # rounded, no float32 noise
    assert np.isnan(df.streamflow.iloc[2])  # fill value
    assert (df.valid_time == pd.Timestamp("2026-04-19 01:00")).all()
    assert (df.nwm_version == "v3.1").all()


def test_single_chunk_layout(fs):
    path = make_ref(fs, "/a.json", [1, 2, 3, 4, 5], T0, version="v3.0", chunk=5)
    df = nwm_kerchunk.read_refs([path], [40], fs=fs, workers=1)
    assert df.streamflow.tolist() == [0.04]


def test_many_files_and_missing(fs):
    paths = [make_ref(fs, f"/{h}.json", [h * 100] * 5, T0 + 60 * h) for h in range(1, 4)]
    with pytest.warns(UserWarning, match="1 reference"):
        df = nwm_kerchunk.read_refs(paths + ["/gone.json"], [10], fs=fs, workers=2)
    assert df.streamflow.tolist() == [1.0, 2.0, 3.0]
    assert df.attrs["missing"] == ["/gone.json"]


def test_unknown_reach(fs):
    path = make_ref(fs, "/a.json", [1, 2, 3, 4, 5], T0)
    with pytest.raises(ValueError, match="99"):
        nwm_kerchunk.read_refs([path], [99], fs=fs, workers=1)


def test_all_missing(fs):
    with pytest.raises(FileNotFoundError):
        nwm_kerchunk.read_refs(["/gone.json"], [10], fs=fs, workers=1)
