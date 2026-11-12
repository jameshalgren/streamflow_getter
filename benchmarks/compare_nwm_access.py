import json
import time
import urllib.request
from pathlib import Path

import fsspec
import numpy as np
import s3fs
import xarray as xr

REACH_ID = 3586192

FILENAME = "nwm.t00z.short_range.channel_rt.f001.conus.nc"

NATIVE_URL = (
    "https://storage.googleapis.com/national-water-model/"
    "nwm.20260419/short_range/" + FILENAME
)

REFERENCE_PATH = (
    "ciroh-nwm-zarr-copy/national-water-model/"
    "nwm.20260419/short_range/" + FILENAME + ".json"
)

LOCAL_FILE = Path("benchmarks/data/nwm_short_range_f001.nc")


def extract_flow(ds):
    ids = ds.feature_id.values
    matches = np.flatnonzero(ids == REACH_ID)

    if len(matches) != 1:
        raise ValueError(f"Expected one match for {REACH_ID}")

    index = int(matches[0])
    flow = float(ds["streamflow"].isel(feature_id=index).values)

    return flow


def benchmark_kerchunk():
    start = time.perf_counter()

    s3 = s3fs.S3FileSystem(anon=True)

    with s3.open(REFERENCE_PATH, "rb") as file:
        reference = json.load(file)

    fs = fsspec.filesystem(
        "reference",
        fo=reference,
        remote_protocol="https",
        remote_options={"asynchronous": True},
        asynchronous=True,
    )

    ds = xr.open_zarr(
        fs.get_mapper(""),
        consolidated=False,
        zarr_format=2,
    )

    try:
        flow = extract_flow(ds)
    finally:
        ds.close()

    return flow, time.perf_counter() - start


def benchmark_native_local():
    start = time.perf_counter()

    with xr.open_dataset(LOCAL_FILE, engine="h5netcdf") as ds:
        flow = extract_flow(ds)

    return flow, time.perf_counter() - start


def benchmark_native_download():
    start = time.perf_counter()

    LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)

    urllib.request.urlretrieve(NATIVE_URL, LOCAL_FILE)

    with xr.open_dataset(LOCAL_FILE, engine="h5netcdf") as ds:
        flow = extract_flow(ds)

    return flow, time.perf_counter() - start


def main():
    results = {}

    for name, function in [
        ("Kerchunk remote", benchmark_kerchunk),
        ("Native local", benchmark_native_local),
        ("Native download + read", benchmark_native_download),
    ]:
        print(f"Running {name}...", flush=True)

        flow, elapsed = function()
        results[name] = (flow, elapsed)

        print(f"  Streamflow: {flow:.10f} m³/s")
        print(f"  Elapsed: {elapsed:.3f} seconds")

    flows = [value[0] for value in results.values()]

    print("\nNumerical agreement:", np.allclose(flows, flows[0]))

    print("\nSummary:")
    for name, (flow, elapsed) in results.items():
        print(f"{name:25} {elapsed:8.3f} s")


if __name__ == "__main__":
    main()
