"""NWM CONUS retrospective streamflow from the public AWS zarr stores."""

import numpy as np
import pandas as pd
import xarray as xr

CHRTOUT_URLS = {
    "3.0": "s3://noaa-nwm-retrospective-3-0-pds/CONUS/zarr/chrtout.zarr",  # 1979-02 to 2023-02
    "2.1": "s3://noaa-nwm-retrospective-2-1-zarr-pds/chrtout.zarr",  # 1979-02 to 2020-12
}


def open_chrtout(version: str = "3.0") -> xr.Dataset:
    return xr.open_zarr(CHRTOUT_URLS[version], storage_options={"anon": True})


def gages_to_reaches(gages: list[str], ds: xr.Dataset) -> dict[str, int]:
    """Map gage IDs (kept as strings, 8-digit USGS zero-padded) to feature_ids."""
    ids = np.char.strip(ds.gage_id.values.astype(str))
    found = {}
    for gage in gages:
        padded = gage.zfill(8) if gage.isdigit() and len(gage) < 8 else gage
        hits = np.flatnonzero(ids == padded)
        if len(hits) == 0:
            raise ValueError(f"gage_id not in NWM CONUS retrospective: {gage}")
        found[gage] = int(ds.feature_id.values[hits[0]])
    return found


def fetch(
    reach_ids: list[int],
    start: str,
    end: str,
    variable: str = "streamflow",
    ds: xr.Dataset | None = None,
) -> pd.DataFrame:
    """Return a long-format frame: time, feature_id, <variable> (m3/s, UTC)."""
    ds = open_chrtout() if ds is None else ds
    missing = sorted(set(reach_ids) - set(ds.feature_id.values.tolist()))
    if missing:
        raise ValueError(f"feature_id not in NWM CONUS retrospective: {missing}")
    sub = ds[variable].sel(feature_id=reach_ids, time=slice(start, end))
    return sub.to_dataframe().reset_index()[["time", "feature_id", variable]]
