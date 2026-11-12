"""Compare Kerchunk reference caching strategies."""

import argparse
import json
import statistics
import time
from pathlib import Path

import fsspec
import s3fs
import xarray as xr

from http_trace import trace_http_reads

REFERENCE_PATH = (
    "ciroh-nwm-zarr-copy/national-water-model/"
    "nwm.20260419/short_range/"
    "nwm.t00z.short_range.channel_rt.f001.conus.nc.json"
)

CACHE_FILE = (
    Path.home()
    / ".cache/streamflow_getter/references"
    / "nwm.20260419/short_range"
    / "nwm.t00z.short_range.channel_rt.f001.conus.nc.json"
)

REACH_INDEX = 351819
EXPECTED_FLOW = 0.40999999083578587


def download_reference():
    s3 = s3fs.S3FileSystem(anon=True)

    with s3.open(REFERENCE_PATH, "rb") as f:
        return f.read()


def read_streamflow(reference):
    with trace_http_reads() as calls:
        fs = fsspec.filesystem(
            "reference",
            fo=reference,
            remote_protocol="https",
            remote_options={"asynchronous": True},
            asynchronous=True,
            skip_instance_cache=True,
        )

        with xr.open_zarr(
            fs.get_mapper(""),
            consolidated=False,
            zarr_format=2,
        ) as ds:
            flow = float(
                ds.streamflow.isel(feature_id=REACH_INDEX).values
            )

    return flow, sum(c["bytes_returned"] for c in calls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["none", "memory", "disk"],
        required=True,
    )
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()

    if args.trials < 1:
        parser.error("--trials must be at least 1")

    memory_reference = None
    times = []

    for trial in range(1, args.trials + 1):
        start = time.perf_counter()
        downloaded_bytes = 0

        if args.mode == "none":
            raw = download_reference()
            downloaded_bytes = len(raw)

        elif args.mode == "memory":
            if memory_reference is None:
                raw = download_reference()
                memory_reference = json.loads(raw)
                downloaded_bytes = len(raw)
            reference = memory_reference

        else:
            if CACHE_FILE.exists():
                raw = CACHE_FILE.read_bytes()
            else:
                raw = download_reference()
                downloaded_bytes = len(raw)
                CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                CACHE_FILE.write_bytes(raw)

        if args.mode != "memory":
            reference = json.loads(raw)

        flow, chunk_bytes = read_streamflow(reference)
        elapsed = time.perf_counter() - start

        if abs(flow - EXPECTED_FLOW) > 1e-6:
            raise ValueError(f"Unexpected streamflow: {flow}")

        times.append(elapsed)

        print(
            f"{args.mode:7} trial={trial} "
            f"time={elapsed:.3f}s "
            f"reference_download={downloaded_bytes} "
            f"chunk_bytes={chunk_bytes}"
        )

    print(
        f"\nMedian: {statistics.median(times):.3f}s"
    )


if __name__ == "__main__":
    main()
