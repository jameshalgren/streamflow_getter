# NWM notes

Collected from the `troute-lab` Basin explorer (`~/git/troute-lab/explorer/`)
and related local repos. File paths and line numbers cited by a search agent
are unverified; check them before relying on them.

## Reach IDs
- CONUS `feature_id` = NHDPlusV2 COMID. IDs >= 1e9 are non-NHDPlus segments.
- Alaska uses NHDPlus HR / Arc-Hydro IDs; Hawaii and PR/VI use NHDPlus V2.1.
- Keep gage IDs as strings (some USGS IDs need a leading zero; some are
  Water Survey of Canada IDs).
- NextGen <-> NWM crosswalk: `~/git/nwmxwalk` (VPU 03W only, lossy; averaging
  many COMIDs per nexus biases flow low). Out of scope for now.

## Data sources
- Retrospective v3.0 (used now): `s3://noaa-nwm-retrospective-3-0-pds/CONUS/zarr/chrtout.zarr`,
  hourly, 1979-02 to 2023-02. Also Alaska, Hawaii, PR; netcdf and zarr.
- Retrospective v2.1: `noaa-nwm-retrospective-2-1-pds`, `noaa-nwm-retrospective-2-1-zarr-pds`.
- Operational: GCS `national-water-model` (back to 2018-09-17); S3
  `noaa-nwm-pds` (back to 2025-01-01).
  Files: `nwm.YYYYMMDD/{run}/nwm.tCCz.{run}.channel_rt.{fHHH|tmHH}.{domain}.nc`.
- `channel_rt` variables: streamflow, velocity, nudge, qSfcLatRunoff, qBucket,
  qBtmVertRunoff (long range: streamflow, nudge, velocity only).

## Gotchas
- chrtout zarr chunks are [672 time x 30000 reach]: read long time ranges
  for few reaches.
- Units m3/s (USGS is cfs, x0.0283168). Time is UTC; use the valid time in the
  file, not the file name. Long-range files can sit in the previous day's folder.
- Operational `channel_rt` files have no lat/lon. `streamflow` is int32 with
  scale_factor 0.01, _FillValue -99990; let xarray decode.
- Without a USGS API key, requests get HTTP 429 and gages silently drop out.
- Browser CORS works on `noaa-nwm-pds` and the GCS JSON API, not direct GCS
  URLs. Matters for the single-page site.

## Prior art
The CIROH Data Access page (https://hub.ciroh.org/docs/products/data-management/dataaccess/,
"Version 2.1" section) has a demo script that pulls reach time series from
`s3://noaa-nwm-retrospective-2-1-zarr-pds/chrtout.zarr` into per-reach CSVs. It
indexes time by hours since 1979-02-01; we select by label instead. More
notebooks: https://github.com/CIROH-UA/data_access_example/.
Both retrospective stores carry a `gage_id` coordinate (~8,000 gages,
8-digit zero-padded USGS IDs); v2.1 ends 2020-12-31, v3.0 ends 2023-02-01.
