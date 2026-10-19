"""NWM v3.0 retrospective (CONUS) streamflow from the public AWS zarr store."""

import pandas as pd
import xarray as xr

CHRTOUT_URL = "s3://noaa-nwm-retrospective-3-0-pds/CONUS/zarr/chrtout.zarr"


def open_chrtout(url: str = CHRTOUT_URL) -> xr.Dataset:
    return xr.open_zarr(url, storage_options={"anon": True})


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
