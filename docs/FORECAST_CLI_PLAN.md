# Plan: Kerchunk-based NWM forecast CLI (initial try)

**Main initial goal:** provide a reasonably efficient tool for getting forecast data from the NWM, for comparison to the output of a to-be-published routing-only datastream from NRDS.CIROH.ORG. Side quests are permitted after that goal is reached, or where they are on the critical path for it.

## Context

- `streamflow-getter nwm` only reads the retrospective Zarr (`src/streamflow_getter/nwm.py`; possibly rename to `nwm_retro.py`).
- `docs/ROADMAP.md` calls for operational forecasts: all products, Kerchunk first, native NetCDF fallback, default t0 from `analysis_assim`.
- `nwmurl` has some of the needed helpers, but v1.0.8 is out of date for current NWM configurations. Plan: fork and update it, operate off our fork until a PR is complete.
  - The CIROH Kerchunk upload process (@karnesh) uses `nwmurl`, so updates must keep it working. @jordanlasergit may also use it for the NextGen research datastream tools.
- This may overlap with [nwmTools](https://mikejohnson51.github.io/nwmTools/) and [hydrotools](https://pypi.org/project/hydrotools/), but probably not: neither uses the Kerchunk files. (They once did; see [teehr-hub#413](https://github.com/RTIInternational/teehr-hub/issues/413).)

## Deliverables (on approval)

- `docs/FORECAST_CLI_PLAN.md`: this document, the editable plan.
- `notebooks/forecast_demo.ipynb`: demonstrates every command below, using only the 2026-04-19 Alabama forecast and a couple of reaches or gages.

Eventually, but not yet: library and CLI code. For now the focus is plan plus notebook demo.

## Proposed CLI

Add a `forecast` subcommand next to `nwm`, plus helpers.

```
streamflow-getter forecast fetch   --product short_range --cycle 2026-04-19T12 \
        --gage 02428400 --reach 101 --member 1 --domain conus \
        --variable streamflow --source auto --no-t0 --out out.parquet
streamflow-getter forecast urls    ...same selectors...   # print resolved files/refs, no download
streamflow-getter forecast list    --date 2026-04-19 [--product ...]   # which cycles/products exist
streamflow-getter forecast refs    build|update|clear ...  # manage local Kerchunk cache
streamflow-getter forecast bench   ...                     # Kerchunk vs native timing and bytes
```

Selection (mutually exclusive groups):

- `--cycle T` (one forecast cycle), `--start/--end` (all cycles in a range), or `--last N[h|d]` (recent days).
- Events (SEED/CSES) are added later as `--event NAME`, which expands to a date range plus reaches.

Other options:

- `--product`: `analysis_assim`, `short_range`, `medium_range`, `long_range`, and the `_no_da`, `_alaska`, `_hawaii`, `_puertorico` variants. Validated against a version-aware table, not free text.
- `--member`: for medium and long range ensembles. Default is all members; `mem1` is the control.
- `--lead`: limits forecast hours (e.g. `1-18`).
- `--no-t0`: skips the `analysis_assim` tm00 row.
- `--source auto|kerchunk|native`: `auto` tries Kerchunk, falls back to native files, and reports which was used.
- `--out`: format inferred from the extension (`.csv`, `.parquet`).

Output is long format and matches `nwm.fetch`, with extra columns: `reference_time` (cycle), `lead_hours`, `valid_time`, `member`, `product`, `source_product`, `feature_id`, `<variable>`.

- t0 rows have `lead_hours=0` and `source_product=analysis_assim`.
- Use the file's `valid_time`, not the filename.

## Architecture

New modules in `src/streamflow_getter/`, each exposing a small, testable function, following the existing adapter style:

- `nwm_catalog.py`: version-aware table of products, domains, cycles, horizons, members, filename patterns, and per-day folder oddities. Replaces what we would otherwise take from `nwmurl`. Pure functions, unit-tested without network access.
- `nwm_urls.py`: `resolve(selection) -> list[FileRef]`, producing native S3/GCS/NOMADS URLs and the matching Kerchunk JSON path (`s3://ciroh-nwm-zarr-copy/national-water-model/nwm.YYYYMMDD/<product>/<file>.nc.json`). Starts as a thin wrapper calling into the `nwmurl` fork once it exists.
- `nwm_kerchunk.py`: build, cache and open references (cache `~/.cache/streamflow_getter`, configurable; combine one cycle's files with `MultiZarrToZarr` along lead time).
- `nwm_forecast.py`: `fetch_forecast(selection, reach_ids, variable, source)`, handling fallback, the t0 attach (fetched once and shared across ensemble members), and long-format assembly.
- `cli.py`: add the `forecast` subparser. Keep the existing `nwm` command unchanged.

Reuse `nwm.gages_to_reaches` for gages (retrospective dataset) with RouteLink for operational reaches, since `channel_rt` has no gage IDs.

## nwmurl fork

Fork the library to the BYU/CIROH org and vendor it as an optional dependency first. Upstream PRs come after our table stabilises. Working branch: <https://github.com/jameshalgren/nwmurl>.

- TODO: confirm where the local working copy lives, or clone it.

Updates needed: current configurations (including `no_da`, per-domain `analysis_assim`, ensemble members), version cutover dates, the long-range previous-day folder quirk, and GCS vs S3 vs NOMADS bases. A long-form issue describing all of this is needed for the update to work against. @jameshalgren is assigned.

### Decision to confirm: where does the catalog live?

**Options:**

1. **Catalog lives in this repo (`nwm_catalog.py`); the fork is a drop-in URL generator tested against it.** We control the table and can iterate fast. The fork stays small, and `nwmurl` users get fixes without taking on our schema.
2. **Catalog lives in `nwmurl`; this repo imports it.** The table becomes a community resource that the CIROH Kerchunk pipeline and the NextGen datastream tools also benefit from. The cost is coupling our iteration speed to upstream review and release cycles.
3. **Hybrid:** start with option 1 so we can move quickly, keeping `nwm_catalog.py` pure data plus pure functions with no streamflow-getter imports, so it can be moved into `nwmurl` wholesale once the table stabilises.

**Decision: option 3 (hybrid).** It matches the "operate off our fork until a PR is complete" plan and keeps the community-resource goal open. `nwm_catalog.py` must stay free of streamflow-getter imports so it can be moved into `nwmurl` wholesale once the table stabilises.

## Archive layout facts

Source: T-Route-Paper session, verified on NOMADS `nwm.20261029` (131,603 files, sizes cross-checked on S3). Details in `/Users/halgren/git/troute_paper/repro/nwm_scale/`: `README.md`, `configs.csv` (one row per config), `expected/nomads_catalog.csv`, `expected/nomads_channel_rt_cycles.csv`, `catalog_nomads.py` (filename regex at line 47), `dt_sources.csv`. Seed `nwm_catalog.py` from `configs.csv` rather than retyping it.

### URL structure

- NOMADS base: `https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwm/prod/nwm.YYYYMMDD/<directory>/<file>`. The S3 mirror `https://noaa-nwm-pds.s3.amazonaws.com/` has the identical key layout.
- Filename regex (verified on all files):
  `^nwm\.t(CC)z\.(run)\.(product)(_MEM)?\.((tm|f)NNN\.)?(domain)(\.sub)?\.(nc|shef)$`
- Domain token: `conus|alaska|hawaii|puertorico`. Products: `channel_rt`, `land`, `reservoir`, `terrain_rt` (forcing dirs: `forcing`; coastal: `total_water`).
- The member suffix sits on the product (`medium_range.channel_rt_2`, `long_range.channel_rt_3`). Inconsistency: pre-ensemble medium-range simulations have no member suffix.
- Directories: CONUS has no suffix; other domains insert `_alaska|_hawaii|_puertorico` (e.g. `analysis_assim_alaska`, `medium_range_alaska_mem3`, `medium_range_blend_alaska`, `analysis_assim_extend_alaska_no_da`). 70 directories in all, of which 40 are model dirs with `channel_rt`.
- **Gotcha:** the run token in the filename is the base run name, not the directory name (files in `medium_range_alaska_mem2/` use run `medium_range`, domain `alaska`).

### Versions

- NWM v3.1 has been operational since ~2026-08-18 12Z (NWS SCN 26-64). `prod/` and `v3.1/` list the same days; `v3.0/` stops at `nwm.20260818`.
- v3.1: PR short range now runs 00/06/12/18; medium-range coastal cut to 120 h; the PR P-surge coastal run appears only when Psurge forcing exists.
- Medium range has 6 members (`mem1`-`mem6`); `mem7` was removed in v3.0 and requests return HTTP 403. Added in v3.0: `medium_range_blend` (NBM-forced). The 7-member medium range and `medium_range_memM` directories date from v2.0.
- `nwmurl` 1.0.8 is stale in three verified ways: no Alaska, 7-member medium-range memdict (`range(2, 8)`), PR short range at 06/18 only. These are the first fixes for the fork.
- Implication for our `--version` option: `3.0`/`2.1` today refer to the retrospective. Operational forecasts need a version axis **derived from the date** (v3.1 cutover 2026-08-18 12Z) rather than chosen by the user, with an override.

### Retention and archives

- NOMADS keeps only two days (today and yesterday): live-use only, not an archive. S3 and GCS archives are needed for any history.
- S3 `noaa-nwm-pds`: the registry promises only a rolling four-week archive ([registry](https://registry.opendata.aws/noaa-nwm-pds/)), but in practice (checked 2026-11-02) the bucket holds 671 day folders from `nwm.20250101` to `nwm.20261102`, including 2026-04-19. The CIROH Kerchunk refs and GCS also still have 2026-04-19. Treat the longer retention as observed, not guaranteed. This matches the `bench-kerchunk` benchmark (`docs/benchmarks/kerchunk-vs-native.md`).
- GCS coverage starts 2018-09-17.
- **Not verified (TODO):** GCS bucket `national-water-model`, NCAR, the retrospective buckets, and any web-archived copies.

### Cycles, horizons, cadence (`channel_rt`; routing dt is 300 s everywhere)

| Domain | Config | Cycles | Range / cadence |
|---|---|---|---|
| CONUS | analysis_assim | 24/day | tm02..tm00, hourly |
| CONUS | analysis_assim_extend | t16z only | tm27..tm00 (28 h) |
| CONUS | analysis_assim_long | 00/06/12/18 | tm11..tm00 (12 h), not hourly |
| CONUS | short_range | 24/day | f001..f018 |
| CONUS | medium_range_mem1 | 00/06/12/18 | f001..f240 hourly |
| CONUS | medium_range_mem2..6 | 00/06/12/18 | f001..f204 hourly |
| CONUS | medium_range_no_da | 00/06/12/18 | f003..f240, 3-hourly |
| CONUS | medium_range_blend | 00/06/12/18 | f001..f240 hourly |
| CONUS | long_range_mem1..4 | 00/06/12/18 | f006..f720, 6-hourly |
| Alaska | analysis_assim | 24/day | tm02..tm00 |
| Alaska | analysis_assim_extend | t20z only | tm31..tm00 (32 h) |
| Alaska | short_range | 00/06/12/18 -> f001..f015; 03/09/15/21 -> f001..f045 (same directory) | hourly |
| Alaska | medium_range mem1 / mem2-6 / no_da / blend | 6-hourly cycles | 240 h / 204 h / 3-hourly / 240 h |
| Hawaii | analysis_assim | 24/day | tm0245..tm0000, 15-min stamps (`tmHHMM`) |
| Hawaii | short_range (+ `_no_da`) | 00/12 | f00015..f04800, 48 h |
| Puerto Rico | analysis_assim | 24/day | tm02..tm00 |
| Puerto Rico | short_range (+ `_no_da`) | 00/06/12/18 | f001..f048 |

Every analysis config has an `_no_da` twin. Hawaii and PR have no medium or long range because their streams are so short and the CFS runs do not capture the relevant orographic and convective physics.

Analysis cycles re-run their whole look-back from a restart, so windows overlap and are recomputed (`model_initialization_time = cycle - KHOUR`, with KHOUR 3/28/32/12). This matters for the default t0: tm00 of the cycle is the value valid at the cycle time.

> **DEEP DIVE (separate white paper, see Side quests):** analysis-cycle time stamps. See below.

`feature_id` count per file matches RouteLink: CONUS 2,776,734; Alaska 391,528; Hawaii 13,637; PR 14,017.

- TODO: check this going back in time; it may differ for older runs and model versions.

Layout, horizons, cadence and output times have all seen minor changes across versions. Building a version history of the table above and storing it as an artifact in the repo would be a valuable outcome.

### Gotchas the catalog and URL builder must encode

- Cadence differs by product within the same run: medium range `land`/`terrain_rt` are 3-hourly and `reservoir` is hourly; long range `land` is daily (1440 min) and `channel_rt`/`reservoir` are 6-hourly; `medium_range_no_da` channel_rt starts at f003.
- `_no_da` dirs hold only `channel_rt`, and those files carry `dev_channel_only = 1`.
- Alaska short range mixes 15 h and 45 h cycles in one directory.
- Hawaii time stamps are 4-digit HHMM; other domains use 2-3 digits.
- A day directory can be partial: check the last cycles (t23z analysis, t18z long range) before treating a day as complete.
- Fetching NOMADS: `curl -s` over HTTP/2 returned 200 with a 0-byte body. Use `curl --http1.1` with a browser User-Agent, or Python `urllib` with a browser UA (applies to `requests`/`fsspec` HTTP too).

### Other facts from our own docs

- Long-range files can live in the previous day's folder (`docs/nwm-notes.md`); the T-Route session saw them in the day folder on 2026-10-29, so verify per archive.
- CIROH Kerchunk references: one ~11 KB JSON per NetCDF file at `s3://ciroh-nwm-zarr-copy/national-water-model/nwm.YYYYMMDD/<product>/<file>.nc.json`. Older `nwm.2022*`/`2023*` folders use a different layout.
- `streamflow` is int32 with scale 0.01 and `_FillValue` -999900 (-9999.0 m3/s decoded). Checked in v3.0 and v3.1 files. Round decoded flow to 2 decimals to remove float32 scale-factor noise.
- v3.1 files (from 2026-08-18) rechunk `streamflow` into 3 chunks of 925,578 reaches and `feature_id` into 6. The Kerchunk reader must handle N chunks per variable and ideally fetch only the chunks holding the requested reaches.
- `analysis_assim` tm00 files carry `reference_time = cycle - 3 h` (model init time), so compute lead time from the cycle, not the file's `reference_time`.
- Reading refs on Windows: the working approach in `scripts/pull_nwm_short_range.py` is a sync fsspec `ReferenceFileSystem(remote_protocol="https")` with `rfs.cat` and numcodecs decode. xarray/zarr async reads segfault at exit on Windows, and zarr rejects a sync filesystem.

## What this changes in the plan

- `nwm_catalog.py` needs `domain` and `directory` fields separate from `run`. `--product` should be a directory-level name (`short_range_alaska`) with `--domain` derived, or we accept both and validate.
- The cycle selector must understand per-config cycle sets (e.g. Alaska 03/09/15/21 with 45 h, Hawaii 00/12 only) and 15-minute lead times.
- **Lead-time representation (answering the float question):** yes, a float would allow 4.25 h for the 15-minute HI cycles, but float matching is fragile (date math could yield 4.249 and miss the file). Proposal: store and compare lead time as **integer minutes** internally (`lead_minutes`), parse CLI input (`--lead 1-18`, `4.25`) by rounding to the nearest minute, and expose `lead_hours = lead_minutes / 60` only in the output. Matching against filename stamps is then exact integer comparison.
- The "default t0 from analysis_assim" must pick the matching-domain tm00 file, and the `_no_da` twin for `_no_da` products. The roadmap's open question is answered: tm00 is valid at the cycle time for hourly analysis (24 cycles/day). Long-range and Hawaii cadences still need checking.
- `forecast list` should report partial days.
- The `nwmurl` fork's first changes: add Alaska, fix the medium-range member set (1-6) and PR short-range cycles, add `medium_range_blend`, and add the v3.1 cutover.

## Side quests

- **Analysis-cycle time-stamp deep dive and community-facing white paper.**
  - Build a table of tm00/tm01/tm02 (and the equivalents across all AnA runs: extend, long, AK, HI, PR) showing which times they correspond to and which date-stamps appear inside the files.
  - Investigate the outstanding hour-shift problem in the T-Route parity experiment led by Aubrey Kohler. NetCDF-internal time stamps may not mean what is assumed, and T-Route's interpretation may be wrong.
  - Known case: WRF-Hydro `chrt_out` files marked f001 refer to output from the *prior* hour, but T-Route treats f001 as the first file and uses its `q_lateral` as the forcing for the next hour (the routing output is only a comparison value for now).
  - Check the rest of the file structures for anomalies, and ask specifically how T-Route handles the hours.
- **Version history of the catalog table**, stored as an artifact in the repo.
- **Improve the CIROH Kerchunk generation code**: update, optimize with newer library versions, suggest a cleaned-up layout, submit a PR.

## Notebook outline (`notebooks/forecast_demo.ipynb`)

Rich markdown headings and descriptions for each section, with images of expected tables, graphs or other output.

1. Setup, and what `forecast urls` resolves for 2026-04-19 short range.
2. `forecast list` for the day.
3. `forecast fetch` with a gage, with and without t0, comparing Kerchunk and native.
4. Medium-range ensemble members plotted as spaghetti, with t0 marked.
5. `forecast bench`: Kerchunk vs native time and bytes read.
6. Cache management (`refs build/clear`).

Each step is shown as the CLI command (via `subprocess`/`!`), then the Python API call for the same thing. The notebook needs the network, so it is not run in CI; the committed cell outputs are from a local run.

## Decisions

- Parquet and CSV both, inferred from the extension. **Confirmed.**
- Notebook directory: `notebooks/`. **Confirmed.**
- `forecast` separate subcommand vs. folding into `nwm` as `--forecast`: **experiment.** Retrospective data is fundamentally different from, though very similar to, forecasts.
- Catalog location relative to the `nwmurl` fork: **hybrid.** Start in this repo as a dependency-free module, move into `nwmurl` once the table stabilises (see above).

## Verification

- `uv run pytest`: new unit tests for `nwm_catalog`/`nwm_urls` use synthetic selections, with no network access.
- Manual: run `forecast urls` and `forecast fetch` for the 2026-04-19 cycle and compare the Kerchunk result with the native files.
- Execute the notebook top to bottom.

## Suggested implementation order

1. Catalog plus URL resolver with tests; the `urls` and `list` commands.
2. Native-file `fetch` with t0 handling and Parquet output.
3. Kerchunk reader and cache, `auto` fallback, then `bench`.
4. Notebook, then the `nwmurl` fork and upstreaming.
