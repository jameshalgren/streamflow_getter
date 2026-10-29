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

## Model versions (operational CONUS)
Measured 2026-10-28 from the `NWM_version_number` attribute in each file.
- **v3.0 -> v3.1 on 2026-08-18**, code_version v5.4.0. The switch is per file:
  on 2026-08-18 the t04z and t09z `analysis_assim` cycles still say v3.0.
  Read the version from each file; don't infer it from the date.
- **No v3.1 retrospective exists** (Russ Barton, NOAA OWP, email of
  2026-09-22). v3.0 retrospective statistics remain the ones in use.
- **Same reaches in v3.0 and v3.1**: the v3.0 retrospective, RouteLink
  v3.1.6, and v3.0 and v3.1 `channel_rt` files all hold the same 2,776,734
  `feature_id`s. The retrospective and forecast files list them in the same
  sorted order; the RouteLink file does not, so match it by ID.
- **lat/lon** are identical between the v3.0 retrospective and RouteLink
  v3.1.6, so retrospective coordinates label v3.1 forecasts correctly.
- **Gage tags changed**: the v3.0 retrospective `gage_id` has 8,660 tagged
  reaches, RouteLink v3.1.6 `gages` has 8,735 (564 added, 489 removed, 4
  changed; e.g. 166764152 `04216000` -> `02HA013`, a Water Survey of Canada
  gauge). Use the gage tags of the version that produced the forecast. We
  have no operational v3.0 RouteLink, so the retrospective stands in for it.
- **v3.1 files are rechunked**: v3.0 stores each variable as one HDF5 chunk
  of all reaches (`streamflow` ~2 MB compressed). v3.1 splits `streamflow`
  into 3 chunks of 925,578 reaches (~0.55 MB each) and `feature_id` into 6
  of 462,789. Few-reach reads in one region fetch about a third as much.
- RouteLink v3.1.6 (from NCO `nwm.v3.1.6/parm/domain/`) and v2.0/v2.1 copies
  are in `~/git/troute_paper` (see `repro/network_stats/fetch_data.py` for
  URLs and hashes). v2.1 -> v3.1.6 removed 4 IDs and changed 21 `to` links;
  details in `research/routelink_version_history.md` there.

## Gotchas
- chrtout zarr chunks are [672 time x 30000 reach]: read long time ranges
  for few reaches.
- Units m3/s (USGS is cfs, x0.0283168). Time is UTC; use the valid time in the
  file, not the file name. Long-range files can sit in the previous day's folder.
- Operational `channel_rt` files have no lat/lon. `streamflow` is int32 with
  scale_factor 0.01, _FillValue -999900 (-9999.0 m3/s once decoded; checked
  2026-10-28 in v3.0 and v3.1 files); let xarray decode.
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
