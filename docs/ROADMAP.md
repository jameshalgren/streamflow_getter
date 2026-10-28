# Roadmap: operational NWM data, events, GEOGLOWS

Decisions from planning, 2026-10-19. Update as they change.

## Principles
- Support every NWM product (analysis_assim, short/medium/long range, ensemble
  members, domains), selecting like `nwmurl` does but more reliably.
- Selection is by **event**, **long period**, or **last few days**. An event
  database (SEED/CSES, hub.ciroh.org) comes later; design the date selection
  so an event is just a named date range plus reaches.
- **Kerchunk first** (faster, less bandwidth); **native NetCDF fallback** must
  also work. Pre-process references into a local cache first, as
  `NGIAB_data_preprocess` does.
- Default test case: the **forecast of 2026-04-19** (Alabama event).

- **Forecast t0 from analysis**: when fetching short, medium or long range
  forecasts, by default also fetch t0 from `analysis_assim` (`tm00`, valid at
  the forecast cycle time) so the series reads t0, then the forecast hours.
  Provide an option to turn it off (e.g. `--no-t0`). Mark these rows in the
  output (lead time 0, source product `analysis_assim`).

## Gates (do not start until cleared)
- **GEOGLOWS**: check with Riley Hales first.
- **Further NWM retrospective work**: check with Josh Cunningham first.
- Interviews with both are useful but not initial.

## Findings so far
- S3 `noaa-nwm-pds/nwm.20260419/` exists with all products (also forcing,
  `usgs_timeslices`).
- CIROH Kerchunk references: `s3://ciroh-nwm-zarr-copy/national-water-model/nwm.YYYYMMDD/<product>/<file>.nc.json`
  - Day folders seen 2018-09-17 to 2026-10-18 (2,954 days), including 2026-04-19.
  - One ~11 KB JSON per NetCDF file, 288 in the `analysis_assim` folder of one day.
  - The top-level `nwm.2022*`/`nwm.2023*` folders in the same bucket are an
    older, shorter layout (2022-04 to 2023-09-14, 375 days).
  - The hub page says these "point to Google assets", with a text change
    needed to point at AWS. Page: https://hub.ciroh.org/docs/products/data-management/dataaccess/
- `nwmurl` 1.0.8 installs from PyPI (CIROH library for building NWM URLs).
- Retrospective v3.0 CONUS zarr time axis ends 2023-02-01 as read from the
  store, not 2024. **Confirm with Josh** whether a longer retrospective exists.

## TODO
- [ ] **Document data date ranges** per source/product/domain (GCS from
  2018-09-17, S3 `noaa-nwm-pds` from 2025-01-01, confirmed 2026-10-28;
  CIROH refs to yesterday; retrospectives; GEOGLOWS). Model versions:
  operational v3.0 -> v3.1 on 2026-08-18 (see docs/nwm-notes.md).
- [x] Benchmark Kerchunk vs native files (time, bytes read) for a few reaches;
  test the CIROH references for age/version. Done 2026-10-28:
  [docs/benchmarks/kerchunk-vs-native.md](benchmarks/kerchunk-vs-native.md).
  CIROH refs ~4x faster than native remote reads on v3.0 files, ~2.5-4.5x
  on v3.1 files (rechunked: ~0.55 MB chunks instead of one ~2 MB chunk per
  variable per file). The per-chunk floor remains (re-hosting with new chunking or
  re-running the CIROH Kerchunk process are still options). Refs lag ~1 day
  behind `noaa-nwm-pds`. Still open: a weeks-long run.
- [ ] Local reference cache: build/download Kerchunk refs per date range and
  product once, reuse after (`~/.cache/streamflow_getter`, configurable).
- [ ] Native-file reader as fallback (nwmurl for URLs). h5netcdf byte-range
  reads were slower than whole-file downloads on v3.0 files but faster on
  v3.1 files; choose per version, or default to ranges for current data.
- [ ] Reach resolution for operational data: channel_rt files have no lat/lon
  or gage IDs. Use RouteLink / channel hydrofabric for gage, point, bbox,
  polygon selection. Share with the map later. v3.0 and v3.1 share one reach
  set and lat/lon, so the v3.0 retrospective labels both. Gage tags differ:
  take them from the RouteLink matching each file's version (v3.1.6 for v3.1).
  Topology (upstream/downstream, polygon) needs RouteLink `to`.
- [ ] Output: Parquet alongside CSV (`--format`, inferred from extension).
  Keep forecast reference time and lead time as columns, not just valid time.
- [ ] Handle model-version changes across 2018-2026 (variables, reach sets,
  chunking). v3.0 -> v3.1 checked (same reaches, new gage tags, rechunked);
  2.0 -> 2.1 -> 3.0 not yet. Readers must not assume one chunk per variable.
- [ ] Event database integration (SEED/CSES): named events as date range + reaches.
- [ ] Interviews: Josh Cunningham (NWM retrospective), Riley Hales (GEOGLOWS).

## Open questions on t0
- Confirm `analysis_assim` `tm00` is valid at the same time as the cycle
  reference time for every product and cycle (short: hourly; medium and long:
  6-hourly), and that each cycle has a matching analysis file.
- Same t0 for all ensemble members (medium/long range): fetch once, attach to
  each member.
- `no_da` forecast variants (e.g. `medium_range_no_da`) pair with
  `analysis_assim_no_da`; non-CONUS domains have their own analysis products.

## Order of work
1. ~~Benchmark Kerchunk vs native on the 2026-04-19 forecast.~~ Done.
2. Reach resolution (RouteLink).
3. Operational fetch: Kerchunk path, then native fallback, then cache.
4. Parquet output.
