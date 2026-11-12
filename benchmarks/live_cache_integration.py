"""Live integration test for the operational NWM reference cache."""

import json
import time
import urllib.request
from pathlib import Path

import fsspec
import numpy as np
import s3fs
import xarray as xr

from streamflow_getter.reference_cache import load_fresh_reference

DATE = "20260419"
PRODUCT = "short_range"
FILENAME = "nwm.t00z.short_range.channel_rt.f001.conus.nc"

REFERENCE_PATH = (
    f"ciroh-nwm-zarr-copy/national-water-model/"
    f"nwm.{DATE}/{PRODUCT}/{FILENAME}.json"
)

SOURCE_URL = (
    "https://storage.googleapis.com/national-water-model/"
    f"nwm.{DATE}/{PRODUCT}/{FILENAME}"
)

CACHE_FILE = (
    Path.home()
    / ".cache/streamflow_getter/records"
    / f"nwm.{DATE}/{PRODUCT}/{FILENAME}.cache.json"
)

REACH_ID = 3586192
REACH_INDEX = 351819
EXPECTED_FLOW = 0.40999999083578587

s3 = s3fs.S3FileSystem(
    anon=True,
    skip_instance_cache=True,
)


def metadata_provider():
    reference_info = s3.info(REFERENCE_PATH)

    request = urllib.request.Request(
        SOURCE_URL,
        method="HEAD",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        generation = response.headers.get("x-goog-generation")

    etag = reference_info.get("ETag")

    if not etag or not generation:
        raise ValueError("Missing remote object metadata")

    return {
        "reference_etag": etag,
        "source_generation": generation,
    }


def downloader():
    with s3.open(REFERENCE_PATH, "rb") as file:
        raw = file.read()

    print(f"Downloaded reference JSON: {len(raw)} bytes")
    return raw


def main():
    start = time.perf_counter()

    reference = load_fresh_reference(
        CACHE_FILE,
        SOURCE_URL,
        metadata_provider,
        downloader,
    )

    cache_elapsed = time.perf_counter() - start

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
        ids = ds.feature_id.values
        assert int(ids[REACH_INDEX]) == REACH_ID

        flow = float(
            ds.streamflow.isel(feature_id=REACH_INDEX).values
        )

        valid_time = str(ds.time.values[0])
        reference_time = str(ds.reference_time.values[0])

    assert np.isclose(flow, EXPECTED_FLOW)
    assert valid_time.startswith("2026-04-19T01:00:00")
    assert reference_time.startswith("2026-04-19T00:00:00")

    print("\nLIVE CACHE INTEGRATION")
    print("Cache file:", CACHE_FILE)
    print("Cache retrieval elapsed:", round(cache_elapsed, 3), "s")
    print("Reach ID:", REACH_ID)
    print("Streamflow:", flow, "m³/s")
    print("Valid time:", valid_time)
    print("Reference time:", reference_time)
    print("Validation: PASSED")


if __name__ == "__main__":
    main()
