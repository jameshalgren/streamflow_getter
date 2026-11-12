# NWM Operational Retrieval — Research and Validation Progress

**Last updated:** November 11, 2026 (America/Chicago)
**Project:** `streamflow_getter`
**Development branch:** `research/nwm-historical-coverage`
**Requirements:** [Project roadmap](../docs/ROADMAP.md)
**Status:** Operational CONUS retrieval implemented; historical compatibility and scientific validation ongoing.

## 1. Research overview

This report consolidates the experimental evidence, implemented capabilities, and outstanding limitations for National Water Model (NWM) operational streamflow retrieval.

The research evaluates four retrieval methods, Kerchunk reference caching, NWM feature resolution, operational forecast products, historical model compatibility, and end-to-end data export.

The results distinguish three levels of evidence:

- **Implemented:** functionality exists in the production package.
- **Automated validation:** behavior has been tested using controlled or mocked inputs.
- **Real-data validation:** retrieval or processing has been tested using actual NWM data.

Successful retrieval on selected dates does not establish continuous historical coverage, full forecast-horizon compatibility, or hydrologic correctness for every location.

Current automated-test and CI status are recorded in [Development Status](../docs/DEVELOPMENT_STATUS.md).

## 2. Reference dataset and retrieval methods

### 2.1 Reference configuration

| Parameter | Configuration |
|---|---|
| Forecast date | 2026-04-19 |
| Product | `short_range` |
| Cycle | 00 UTC |
| Domain | CONUS |
| Variable | `streamflow` |
| Units | m³/s |
| Forecast leads | f001–f018 |
| Forecast cycles | 24 hourly cycles |
| Channel files for the tested date | 432 |
| Features per file | 2,776,734 |

### 2.2 Retrieval methods

Four retrieval approaches were evaluated:

1. Kerchunk remote references.
2. Native NetCDF through remote HTTP range requests.
3. Full native NetCDF download followed by local reading.
4. Native NetCDF reading from an existing local file.

The benchmarks measured elapsed retrieval time and accounted HTTP response-body bytes. The byte measurements do not include all protocol overhead.

## 3. Retrieval performance

### 3.1 Initial repeated benchmark

Six forecast hours, five trials per method and hour, one NWM reach, and 120 retrieval operations.

| Method | Median retrieval time | Accounted bytes |
|---|---:|---:|
| Native remote | 0.3554 s | 123.89 MB |
| Kerchunk | 0.4753 s | 79.41 MB |
| Native download | 0.6416 s | 429.95 MB |
| Native local | 0.0600 s | 0 |

Byte totals cover 30 operations per remote method.

Native remote retrieval was faster than Kerchunk in this experiment, while Kerchunk required fewer accounted response-body bytes.

### 3.2 Complete 18-hour forecast benchmark

**Configuration:** April 19, 2026; short-range CONUS; cycle 00 UTC; forecast leads f001–f018; five reaches; four methods; one trial per lead.

The experiment produced 72 retrieval operations and 360 streamflow records.

| Method | Median time | Accounted bytes |
|---|---:|---:|
| Native remote | 0.476 s | 74,245,753 |
| Kerchunk | 0.497 s | 47,558,690 |
| Native download | 0.545 s | 257,304,483 |
| Native local | 0.061 s | 0 |

All forecast leads passed the numerical and timestamp comparisons. No duplicate records were detected.

### 3.3 Complete 18-hour benchmark with three trials

**Configuration:** April 19, 2026; short-range CONUS; 18 forecast leads; five reaches; three trials per lead and method.

The experiment produced **216 retrieval operations and 1,080 streamflow records**.

| Method | Median time | Accounted bytes |
|---|---:|---:|
| Kerchunk | 0.482 s | 142,676,070 |
| Native remote | 0.477 s | 222,737,259 |
| Native download | 0.536 s | 771,913,449 |
| Native local | 0.060 s | 0 |

Kerchunk used approximately 35.9% fewer accounted bytes than native remote retrieval and 81.5% fewer than full native downloads.

Kerchunk and native remote retrieval had similar median times. The experiment does not establish a statistically controlled speed advantage.

### 3.4 Three-day benchmark

**Configuration:** April 19–21, 2026; short-range CONUS; cycle 00 UTC; lead f001; five reaches; four methods; one trial per date.

The experiment produced 12 retrieval operations and 60 streamflow records.

| Method | Median time | Accounted bytes |
|---|---:|---:|
| Kerchunk | 0.608 s | 7,865,304 |
| Native remote | 0.632 s | 12,313,146 |
| Native download | 0.501 s | 42,627,027 |
| Native local | 0.060 s | 0 |

Kerchunk used 36.1% fewer accounted bytes than native remote and 81.5% fewer than full native downloads.

All four methods returned matching streamflow and timestamps.

### 3.5 Five-reach benchmark

One forecast lead, one trial, five reaches.

| Method | Elapsed time | Accounted bytes |
|---|---:|---:|
| Native download | 0.595 s | 14,324,480 |
| Native remote | 0.868 s | 4,131,132 |
| Kerchunk | 0.901 s | 2,648,518 |
| Native local | 0.059 s | 0 |

The five tested feature IDs were:

| Feature ID | Array index | f001 streamflow (m³/s) |
|---|---:|---:|
| 1122645 | 100,000 | 7.08 |
| 3586192 | 351,819 | 0.41 |
| 7144704 | 750,000 | 0.00 |
| 14191043 | 1,500,000 | 16,062.71 |
| 23610484 | 2,500,000 | 0.01 |

These positions apply to the tested reference configuration and must not be assumed valid across historical NWM networks.

### 3.6 Benchmark interpretation

The repeated experiments support the conclusion that Kerchunk can substantially reduce accounted data transfer for selected streamflow queries.

They do not establish that Kerchunk is universally faster, because network conditions, cache state, and remote-service behavior were not fully controlled.

Reach-resolution time was excluded from the retrieval benchmarks.

Benchmark output includes:

- `benchmarks/results/repeated_benchmark.csv`
- `benchmarks/results/repeated_benchmark_flows.csv`

See [Benchmark documentation](README.md) for execution procedures.

### 3.7 Verification of archived benchmark results

On November 9, 2026, the existing local CSV pairs for Sections 3.3 and 3.4 were revalidated using implementation commit `5d1db8951f8917e5b77cd2bcff8cf27334a3cda3`. This was validation of stored results, not a new retrieval or performance experiment.

The files below are local generated artifacts under `benchmarks/results/`, covered by the existing Git ignore policy. Their SHA-256 fingerprints were unchanged between inventory and validation.

| File | Rows | SHA-256 |
|---|---:|---|
| `short_range_18h_5reaches_3trials.csv` | 216 | `3aba9e7ce044968245a6276169fa613737e67374aaf91f1608a10584b602dc9e` |
| `short_range_18h_5reaches_3trials_flows.csv` | 1,080 | `09da06e9164d6de8c0561596f1d1c63f1cbff164d4deb069a0c6680ee88850ba` |
| `short_range_20260419_20260421_t00z.csv` | 12 | `44eac1146b2dbf28368bf35f057f686420f18bd67f1b0f6d428f4a8a932a8981` |
| `short_range_20260419_20260421_t00z_flows.csv` | 60 | `d5014dd0c0ebaf3c207d1bee6346e45d8a06cbf02dfd7b304599c6e44126e205` |

Both pairs passed the following checks:

- Complete expected operation and flow keys, with no duplicate, missing, or unexpected combinations.
- Five expected reaches per operation: `1122645`, `3586192`, `7144704`, `14191043`, and `23610484`.
- Finite discharge values, with genuine zeros retained.
- Reference times equal to the selected forecast initialization and valid times equal to initialization plus forecast hour.
- Agreement across all methods and trials within each forecast/lead/reach group, using `rtol=1e-6` and `atol=1e-6`. The observed maximum absolute difference was `0 m3/s` in both experiments.
- Recomputed median retrieval times matched the rounded values in the existing tables, and accounted response-body byte totals matched exactly.

The 18-hour files contain 216 stored zero-valued flow rows; the three-day files contain 12. These counts include repeated method/trial rows. Both datasets have a discharge range of `0` to `16062.709641 m3/s`.

The 18-hour CSVs predate the forecast metadata columns. Their documented context (`2026-04-19`, cycle `00`, `short_range`, `conus`) was supplied only in memory for validation. The three-day CSVs already contain these fields. Both experiments contain forecast leads without analysis t0; the reference-time check above does not define the rule for analysis-derived t0 rows.

This validates the stored coverage, timing, and agreement between retrieval methods for these specific experiments. It does not establish continuous archive coverage, controlled cache performance, or a universal retrieval-speed advantage.

## 4. Reference caching and validation

### 4.1 Cache performance

| Experiment | Median time |
|---|---:|
| Same-process native remote | 0.491 s |
| Separate-process native remote | 0.943 s |
| Kerchunk without reference cache | 0.434 s |
| Kerchunk with memory cache | 0.320 s |
| Kerchunk with disk cache | 0.292 s |

The tested reference JSON contained 7,887 bytes.

Caching avoids repeated reference downloads but does not eliminate retrieval of remote model-data chunks.

A separate live experiment returned:

| Execution | Retrieval time |
|---|---:|
| First retrieval | 0.748 s |
| Cached retrieval | 0.429 s |

Both returned `0.40999999083578587 m³/s` for feature ID `3586192`, valid at April 19, 2026, 01:00 UTC.

These measurements establish cache reuse, not a controlled performance improvement.

### 4.2 Reference validation

The production cache and validation implementation supports:

- Reference structure and external byte-range checks.
- Source URL identity verification.
- ETag and source-generation metadata comparison.
- SHA-256 integrity verification.
- Atomic cache-record persistence.
- Protection against failed refreshes.
- Rejection of unresolved source-generation changes.

The original reference validation experiment inspected 32 reference entries, including seven external byte ranges.

The tested native source size was 14,324,480 bytes; the maximum referenced byte boundary matched that size.

**Limitation:** valid byte ranges, ETag comparisons, and cache integrity do not independently prove that a reference was generated from the current source contents.

### 4.3 Shared reference preparation

`prepare_operational_reference` prepares one validated reference without opening model arrays. The Kerchunk reader reuses this function. `prepare_operational_references` validates a complete collection of forecast configurations before acquisition, applies product-specific schedules and optional analysis t0, and prepares each unique reference path/native URL pair once. See the [preparation API guide](../docs/OPERATIONAL_NWM.md#preparing-a-reference-before-retrieval) for usage, failure behavior, and size-accounting semantics.

The following live cases used different uncommitted working-tree revisions, both based on `e857f6987a07fafe7d3781307c528102bf99199d`:

| Acceptance case | Operational module SHA-256 |
|---|---|
| C4, after single-reference implementation C3 | `bc91a6e66909fb18eff54de87d2bafbdb0da597094e832d9423e05b210b9392e` |
| C6, after batch implementation C5 | `134401dae3d2ae9a8e8c3a2d0304ee77f020fcecdbcac83b8e175106c11dd0f6` |

The acceptance CSVs record the base commit and full four-file working-tree fingerprint maps, source identities, and cache metadata. They remain local generated artifacts under `benchmarks/results/`, covered by the existing CSV ignore rule. Automated-test results are recorded in [Development Status](../docs/DEVELOPMENT_STATUS.md).

### 4.4 Live preparation followed by cached retrieval

Execution UTC: `2026-11-10T16:52:16.884685+00:00`. Selection: CONUS, April 19, 2026, cycle 00, `short_range` f001, reach `3586192`.

Preparation used a new temporary cache with model-data entry points blocked. Subsequent production retrieval used the prepared reference and returned `method="kerchunk"`. Remote freshness metadata was checked during both phases; cached record bytes remained unchanged.

| Phase | Reference-body open calls | Elapsed seconds |
|---|---:|---:|
| Preparation | 1 | 0.870 |
| Retrieval | 0 | 1.695 |

The returned flow was `0.40999999083578587 m3/s`, with reference time `2026-04-19T00:00:00Z` and valid time `2026-04-19T01:00:00Z`. Its absolute difference from both the accepted [live Kerchunk point](#65-live-geographic-retrieval-and-export) and [archived native-download value](#37-verification-of-archived-benchmark-results) was `5.5511151231257827e-17 m3/s`, within `rtol=1e-6` and `atol=1e-6`.

Artifact: `live_reference_preparation_20260419_t00_f001.csv` — 1 row, 1,797 bytes. SHA-256: `2be179764d7d86156c3c72aa47f105084880ead300a3bb4e3e476a854fe013b3`.

This verifies one reference and one reach for one forecast lead. The temporary cache was removed and the implementation files and Git state were preserved. Counts describe reference-body opens, not HTTP requests or transferred bytes; elapsed times provide acceptance context, not a controlled performance comparison. Warm retrieval still requires remote freshness checks and model-data access.

### 4.5 Live batch preparation and reuse

Execution UTC: `2026-11-10T17:47:00.539630+00:00`. Selection: CONUS, April 19, 2026, cycle 00, forecast window f003 plus default analysis t0. Four requested configurations were `medium_range_mem1`, `medium_range_mem2`, `medium_range_no_da`, and a deliberate duplicate of member 1.

Each phase prepared exactly five unique sources, in the following order:

| Source product | Lead hour | Cold preparation calls | Warm preparation calls | Cold reference-body opens | Warm reference-body opens |
|---|---:|---:|---:|---:|---:|
| `analysis_assim` | 0 | 1 | 1 | 1 | 0 |
| `medium_range_mem1` | 3 | 1 | 1 | 1 | 0 |
| `medium_range_mem2` | 3 | 1 | 1 | 1 | 0 |
| `analysis_assim_no_da` | 0 | 1 | 1 | 1 | 0 |
| `medium_range_no_da` | 3 | 1 | 1 | 1 | 0 |

All five cache records validated; their byte snapshots and compact source summaries were unchanged on the warm pass. Remote freshness metadata was checked and source-specific consistency verified in both phases. Model-data entry points were blocked throughout: this case prepared references without decoding flow arrays or timestamps. The temporary cache was removed and the C5 implementation files and Git state were preserved.

Cold/warm batch elapsed times were `3.179` and `1.010` seconds. The totals of five cold and zero warm reference-body opens do not measure HTTP-request counts or network bytes. The timings are acceptance context, not a controlled cache-speed benchmark.

Artifact: `live_batch_reference_preparation_20260419_t00_f003.csv` — 5 rows, 6,231 bytes. SHA-256: `0df34c00443069ed6ea85c72c5d0dcd99a2beb08939572a6e87bf0ed390bfcf5`.

This verifies deduplication of a shared analysis reference and repeated configuration while keeping ensemble forecasts and no-DA sources distinct for this cycle. It does not establish decoded t0 sharing, offline retrieval, complete product/date coverage, or scientific equivalence of forecast initialization states.

### 4.6 Remote reference reliability

The cache implementation distinguishes missing remote references from local storage and integrity failures. `RemoteReferenceNotFoundError` identifies absence at the reference metadata or body acquisition boundary and preserves the original cause. Freshness checks invalidate the relevant in-memory S3 listing entries and request fresh object metadata, preventing stale ETags, false missing-file results, and outdated body-open metadata from those listings. Existing source-generation and before/after consistency checks still govern cache reuse and replacement.

The retrieval coordinator permits cached native fallback only for this missing-reference classification. Other cached errors propagate. Single and batch preparation remain strict and do not invoke native retrieval. See the [operational guide](../docs/OPERATIONAL_NWM.md#reference-caching) for the failure contract.

The D3 automated validation and D4 live case used a working tree based on `f8dde69cd7fa6bb33a3180a5637b4f3bf0d32e1d`, with these production and test fingerprints:

| File | SHA-256 |
|---|---|
| `src/streamflow_getter/reference_cache.py` | `cdc41d30168302a7d99585c94fac2a6cb94d0e606983a84a3bab9021fb7cd646` |
| `src/streamflow_getter/operational_nwm.py` | `26146465a7e9b7cab4438874cf6318f2b8f2cdd9fe1a6c3e86db7fd9df43b773` |
| `tests/test_operational_reference_cache.py` | `11345a5e980b7fa72f4864a9cd483036ee5f747da66e889a66fc0ddda4efdf42` |
| `tests/test_operational_kerchunk.py` | `54e676baecdeb2da966211d7aad2103230d6e2b4254a72e7ccaf7e954da81aa0` |
| `tests/test_operational_fallback.py` | `67cf291e1178dda52759a917887344a51d8b9ea597b1c281b298832fc1cb8620` |

The D4 CSV retains the complete seven-file working-tree map, including the documentation revisions used during that experiment. Subsequent evidence consolidation preserves the production and test fingerprints above. Automated results and publication status are recorded in [Development Status](../docs/DEVELOPMENT_STATUS.md).

### 4.7 Operational CLI cache policy

The operational CLI now implements the roadmap's configurable local reference-cache policy while leaving the lower-level Python API defaults unchanged.

| CLI mode | `cache_dir` passed to retrieval |
|---|---|
| default | `~/.cache/streamflow_getter` |
| `--cache-dir PATH` | the explicit path |
| `--no-cache` | `None` |

`--cache-dir` and `--no-cache` are mutually exclusive.

Automated validation on macOS ARM64 with Python 3.14.6 passed **694 tests in 1.20 seconds**. Five focused policy tests verify parser defaults, CLI propagation, explicit override, explicit opt-out, and conflicting-option rejection.

The live acceptance run used April 19, 2026, cycle 00, `short_range` f001, reach `3586192`, with analysis t0 disabled. The experiment isolated `HOME` in temporary directories so it did not modify the user's actual default cache.

| Run | Method | Flow (m3/s) | Observed cache behavior |
|---|---|---:|---|
| default cold | `kerchunk` | `0.4099999908357858` | created one record under `.cache/streamflow_getter` |
| default warm | `kerchunk` | `0.4099999908357858` | reused the same record unchanged |
| explicit override | `kerchunk` | `0.4099999908357858` | wrote one record only under the requested cache directory |
| `--no-cache` | `kerchunk` | `0.4099999908357858` | created no persistent reference cache |

The maximum flow difference across the four runs was `0.0 m3/s`. All runs retained the same forecast reference and valid times.

The default cache record path was:

`~/.cache/streamflow_getter/nwm.20260419/short_range/nwm.t00z.short_range.channel_rt.f001.conus.nc.cache.json`

Its cold-run cache-file SHA-256 was `1a5d8e4c10d0874a35b269e07c19f6ab86038a24786b428b5fc43efbc819895a`; the warm run left those bytes unchanged.

| Local artifact under `benchmarks/results/` | Rows | Bytes | SHA-256 |
|---|---:|---:|---|
| `live_cli_cache_policy_20260419_t00_f001.csv` | 4 | 1,925 | `eaa0d734ac21b4cb115b69f98d27f591ecce0ff1bb3621e111d855595d5f4e8e` |

Elapsed times in the artifact are acceptance context only and do not establish a cache-speed advantage. This case covers one CONUS short-range cycle, forecast lead, and reach. It does not establish full product/date/domain coverage or offline retrieval.

### 4.8 Operational request planning and multi-configuration execution

The operational request layer now separates request expansion from model-data retrieval.

`plan_operational_configs` expands an inclusive UTC date range into validated `ForecastConfig` objects in deterministic date/cycle/product order without remote access. `resolve_recent_date_range` converts a relative recent-day selection to absolute UTC dates before planning. `OperationalEvent` is an immutable name plus absolute start/end dates, and `plan_operational_event` delegates to the same planner rather than creating a second event-specific NWM path.

`fetch_operational_configs` executes a finite configuration collection through the existing `fetch_operational_series` primitive. It validates all product-specific lead windows before retrieval, uses strict failure behavior, adds `requested_product` to preserve request identity, and decodes analysis t0 once per unique resolved analysis source before attaching the row to each requested product sharing that source. `analysis_assim_no_da` remains separate.

The operational CLI preserves the established single-`--date` path and adds an inclusive `--start-date` / `--end-date` path plus `--recent-days N`. The current CLI intentionally remains one cycle and one product per invocation. The internal `requested_product` field is removed before one-product CLI export so the established output schema is unchanged. Named events remain a Python planning abstraction until the project has a request/run provenance contract capable of retaining the event name.

Local automated validation after the event abstraction: **746 passed in 0.88 seconds**.

#### Live multi-product shared-t0 case

Execution scope: April 19, 2026, cycle 00, f003, reach `3586192`; requested products `short_range`, `medium_range_mem1`, `medium_range_mem2`, and `medium_range_no_da`.

Production retrieval performed exactly six forecast/analysis fetches:

1. `short_range` t0 -> `analysis_assim`
2. `short_range` f003
3. `medium_range_mem1` f003
4. `medium_range_mem2` f003
5. `medium_range_no_da` t0 -> `analysis_assim_no_da`
6. `medium_range_no_da` f003

Thus four requested products required only two actual analysis-t0 decodes. The combined output contained eight rows: t0 plus f003 for each requested product. The three normal products carried identical copied `analysis_assim` t0 science while retaining distinct `requested_product`; no-DA retained `analysis_assim_no_da`.

The live short-range f003 flow was `0.3899999912828207 m3/s`, exactly matching the accepted archived native-download comparison (`0.0 m3/s` absolute difference). Six unique reference-cache records were created in the temporary cache.

| Local artifact under `benchmarks/results/` | Rows | Bytes | SHA-256 |
|---|---:|---:|---|
| `live_multi_config_shared_t0_20260419_t00_f003.csv` | 8 | 29,558 | `78d003e2ffe0413f141f24d282260a56aee2d73f78399e7925e84ee825630fc8` |

#### Live inclusive three-day CLI case

The production CLI requested April 19-21, 2026, cycle 00, `short_range` f001, reach `3586192`, with t0 disabled and a temporary explicit cache.

The CLI returned three rows representing three distinct forecast initializations:

- April 19: `0.4099999908357858 m3/s`
- April 20: `0.3699999917298555 m3/s`
- April 21: `1.1299999747425318 m3/s`

Each initialization retained its own 00Z `reference_time`, 01Z `valid_time`, and separate cache record. All three live Kerchunk flows matched their accepted archived native-download values with `0.0 m3/s` absolute difference.

| Local artifact under `benchmarks/results/` | Rows | Bytes | SHA-256 |
|---|---:|---:|---|
| `live_cli_period_20260419_20260421_t00_f001.csv` | 3 | 3,767 | `330460dfb27e04a96fcd198de7f6aa7f9abba8260c3df9985c1b3d7adaf67d91` |

These live cases validate one date/cycle/lead/reach product group and one three-day short-range period. They do not establish current-date `--recent-days` archive availability, every product/cycle/date combination, a named-event catalogue, or partial-result behavior. Elapsed times in the local evidence are acceptance context rather than performance benchmarks.

### 4.9 Stable operational output provenance and run manifests

Operational retrieval now has an explicit separation between the exported streamflow rows and run-level provenance.

The established one-product CSV/Parquet schema remains unchanged:

- `forecast_date`
- `forecast_cycle`
- `product`
- `domain`
- `lead_hour`
- `feature_id`
- `valid_time`
- `reference_time`
- `streamflow_m3s`
- `method`

The internal combined-request contract additionally carries `requested_product`. Its stable row identity is `forecast_date`, `forecast_cycle`, `requested_product`, `domain`, `lead_hour`, and `feature_id`. `requested_product` records what the request asked for, while `product` remains the actual NWM source product. They match for forecast rows and may differ for analysis t0. Literal source `reference_time` is preserved rather than rewritten to equal the forecast cycle.

Manifest schema version 1 records the resolved temporal selection, planned configurations, reaches, lead window, t0 policy, cache policy, software version, diagnostics, stable output contract, method/source counts, and strict expected-versus-actual row completeness. Version 1 represents complete strict runs only; missing or unplanned row identities cause manifest construction to fail.

Manifest JSON publication is performed from a completely serialized temporary file and refuses to overwrite an existing destination. The combined data-plus-manifest helper validates both destinations before publication and removes a newly created data file if sidecar publication fails. These are in-process rollback semantics rather than a claim of portable two-file crash atomicity.

The operational CLI now writes a sidecar beside every successful operational output:

- `forecast.csv` + `forecast.csv.manifest.json`
- `forecast.parquet` + `forecast.parquet.manifest.json`

The CLI builds the manifest from the internal combined frame before dropping `requested_product`, preserving provenance without changing the established streamflow data schema.

Local automated validation after CLI integration and test-fixture modernization: **780 passed in 1.08 seconds**.

#### Live three-day data + manifest acceptance

Scope: April 19-21, 2026, cycle 00, `short_range` f001, reach `3586192`, t0 disabled, and an explicit temporary persistent reference cache.

The production CLI wrote three streamflow rows plus a strict JSON run manifest. Three separate Kerchunk cache records were created, one for each initialization date.

Live streamflow matched the accepted native-download comparison exactly:

| Forecast date | Live Kerchunk (m3/s) | Accepted native download (m3/s) | Absolute difference (m3/s) |
|---|---:|---:|---:|
| 2026-04-19 | 0.4099999908357858 | 0.4099999908357858 | 0.0 |
| 2026-04-20 | 0.3699999917298555 | 0.3699999917298555 | 0.0 |
| 2026-04-21 | 1.1299999747425318 | 1.1299999747425318 | 0.0 |

The generated manifest recorded:

- status `complete`;
- three expected and three actual row identities;
- zero missing and zero extra rows;
- requested-product counts `{"short_range": 3}`;
- source-product counts `{"short_range": 3}`;
- method counts `{"kerchunk": 3}`;
- explicit-period request dates;
- the resolved reach and lead window;
- t0 disabled;
- the explicit persistent cache directory used by the run.

| Local artifact under `benchmarks/results/` | Rows | Bytes | SHA-256 |
|---|---:|---:|---|
| `live_cli_manifest_period_20260419_20260421_t00_f001.csv` | 3 | 502 | `b8584682fadf4b43e7ec9a2a6b7bb5daa02d2b1b6793b0882bf38ff1b16ed83e` |
| `live_cli_manifest_period_20260419_20260421_t00_f001.csv.manifest.json` | — | 2,279 | `dd5c7a4b02593db7ec959ea8b038e8b4f1dd4ad06635a572270b09c07238ae69` |

The live acceptance scope is deliberately bounded. It verifies one three-day short-range request and does not establish every product/member/cycle, current-date archive availability, partial-result behavior, or crash recovery across two filesystem paths. Elapsed time is acceptance context rather than a performance benchmark.

## 5. Operational NWM implementation

The production implementation uses reusable modules for forecast configuration, source resolution, Kerchunk and native NetCDF retrieval, reach selection, reference validation, caching, and output serialization.

Key modules include:

| Module | Responsibility |
|---|---|
| `operational_nwm.py` | Forecast products, reference preparation, retrieval, timestamps, and series assembly |
| `reference_cache.py` | Reference persistence and reuse |
| `reference_validation.py` | Reference integrity and source checks |
| `reach_resolution.py` | USGS gage to NWM feature mapping |
| `spatial_resolution.py` | Geographic channel selection |
| `output.py` | CSV and Parquet serialization |
| `cli.py` | Command-line integration |

### 5.1 Supported forecast products

| Product | Cycles (UTC) | Modern forecast schedule |
|---|---|---|
| `short_range` | 00–23 hourly | f001–f018, hourly |
| `medium_range_mem1` | 00, 06, 12, 18 | f001–f240, hourly |
| `medium_range_mem2`–`mem6` | 00, 06, 12, 18 | f001–f204, hourly |
| `medium_range_blend` | 00, 06, 12, 18 | f001–f240, hourly |
| `medium_range_no_da` | 00, 06, 12, 18 | f003–f240, every 3 hours |
| `long_range_mem1`–`mem4` | 00, 06, 12, 18 | f006–f720, every 6 hours |

Historical medium-range ensemble schedules differ, as documented in Section 7.

### 5.2 Analysis timestep

The operational CLI includes an analysis timestep (`t0`) by default.

Most supported products use `analysis_assim`. The `medium_range_no_da` product uses `analysis_assim_no_da`.

For the April 19, 2026, cycle 00 UTC reference case:

- Analysis valid time: 2026-04-19 00:00 UTC.
- Analysis reference time: 2026-04-18 21:00 UTC.
- Short-range f001 valid time: 2026-04-19 01:00 UTC.
- Forecast reference time: 2026-04-19 00:00 UTC.

The observed three-hour analysis reference-time offset must not be assumed universal.

Long-range products currently use the shared `analysis_assim` t0 specified in the project roadmap. This is technically validated for selected cases, but its equivalence to the ensemble members' internal initialization states is not established.

The CLI supports `--no-t0`.

### 5.3 Selected product validation

| Product family | Real-data evidence |
|---|---|
| Short-range | Kerchunk/native agreement; CLI retrieval |
| Medium-range members 1–6 | Kerchunk/native agreement at selected f001 leads |
| Medium-range blend | Kerchunk/native agreement at f001; CLI t0–f002 |
| Medium-range no-DA | Correct analysis source; native/Kerchunk agreement for t0 and f003 |
| Long-range members 1–4 | Kerchunk/native agreement at f006; CLI t0, f006, f012 |

The principal modern validation case used April 19, 2026, cycle 00 UTC, feature ID `3586192`.

For `medium_range_no_da`, the tested t0, f003, and f006 values were approximately 0.30 m³/s.

For long-range members 1–4, the tested streamflow values were approximately 0.41 m³/s at t0, 0.33 m³/s at f006, and 0.23 m³/s at f012.

The availability of f720 source objects was sampled, but complete 720-hour retrieval was not validated.

### 5.4 Controlled native-fallback integration

- Execution UTC: `2026-11-10T03:36:14.972298+00:00`.
- Implementation commit: `55c2ab571393429cadb9cf801f89bd5da9493af0`.
- Configuration: `2026-04-19`, cycle `00`, `short_range`, `conus`, lead `f001`, feature ID `3586192`, `cache_dir=None`.

A process-local patch injected `FileNotFoundError` only at `read_kerchunk_forecast`. The unchanged `fetch_operational_forecast` coordinator then performed a real native HTTP-range retrieval through `read_native_forecast`. Exactly one injected call was confirmed, and the original Kerchunk reader was restored afterward.

Native source:

`https://storage.googleapis.com/national-water-model/nwm.20260419/short_range/nwm.t00z.short_range.channel_rt.f001.conus.nc`

The returned method was `native_remote`, with fallback reason `FileNotFoundError: B5 controlled missing-reference injection`.

Validation confirmed the requested forecast metadata and reach, finite discharge, reference time `2026-04-19T00:00:00Z`, and valid time `2026-04-19T01:00:00Z`. Native discharge was `0.40999999083578587 m3/s`. Its absolute difference from each stored comparison value was `5.5511151231257827e-17 m3/s`, within `rtol=1e-6` and `atol=1e-6`.

The comparison records were the live point CSV in Section 6.5 and the archived `native_download` row for trial 1, f001, reach `3586192` in `short_range_18h_5reaches_3trials_flows.csv` (Section 3.7). Both comparison-file fingerprints were verified before retrieval.

The single coordinator call took `1.993 s`. This is acceptance-run context, not a controlled performance benchmark.

The local diagnostic artifact under `benchmarks/results/` is covered by the existing Git ignore policy:

| File | Rows | Bytes | SHA-256 |
|---|---:|---:|---|
| `live_native_fallback_20260419_t00_f001.csv` | 1 | 755 | `a1422fd08205799dd60e254773608bf9ccae0113177c75275eb827b78fade452` |

The diagnostic CSV retains the returned fallback reason, the `controlled_missing_reference` experiment label, and provenance fields. These are acceptance-artifact fields; the production CLI export contract was unchanged.

This validates controlled uncached fallback for the selected case. The missing reference was injected; the experiment does not establish a naturally occurring archive outage, cached-path fallback, or analysis-t0 behavior.

### 5.5 Controlled cached native fallback

Execution UTC: `2026-11-11T02:25:18.957354+00:00` (November 10, 2026, America/Chicago). Selection: CONUS, April 19, 2026, cycle 00, `short_range` f001, reach `3586192`. Implementation provenance is recorded in [Section 4.6](#46-remote-reference-reliability).

A live reference was prepared in a new temporary cache with model-array entry points blocked. During subsequent production retrieval, a process-local `FileNotFoundError` was injected only at the actual S3 filesystem instance's metadata lookup for the exact reference path. The original metadata implementation classified it as `RemoteReferenceNotFoundError`, retaining its cause. The coordinator then called the actual native reader once.

| Phase | Metadata-provider calls | Reference-body opens | Native-reader calls | Elapsed seconds |
|---|---:|---:|---:|---:|
| Preparation | 2 | 1 | 0 | 0.945 |
| Retrieval with injected metadata absence | 1 | 0 | 1 | 8.813 |

The failed retrieval metadata call included one injected lookup. Counts describe Python calls, not HTTP requests or transferred bytes. Elapsed times provide acceptance context, not a controlled performance comparison.

The result was `method="native_remote"`, flow `0.40999999083578587 m3/s`, reference time `2026-04-19T00:00:00Z`, and valid time `2026-04-19T01:00:00Z`. The fallback reason identified `RemoteReferenceNotFoundError` and the exact missing reference path. The absolute difference from both the accepted [live Kerchunk point](#65-live-geographic-retrieval-and-export) and [archived native-download value](#37-verification-of-archived-benchmark-results) was `5.5511151231257827e-17 m3/s`, within `rtol=1e-6` and `atol=1e-6`.

The existing cache bytes and validated manifest remained unchanged. Temporary instrumentation was restored, the temporary cache was removed, and the seven implementation/documentation/test files and Git state were preserved.

| Local artifact under `benchmarks/results/` | Rows | Bytes | SHA-256 |
|---|---:|---:|---|
| `live_cached_native_fallback_20260419_t00_f001.csv` | 1 | 3,025 | `df0a9c916f2b35b5c721d9d244cf1f69898620e5c3317d61b27220d2aab53305` |

The CSV records the controlled injection, source identity, working-tree and comparison fingerprints, prepared cache manifest and record digest, call counts, fallback reason, and flow differences. It remains a local generated artifact under the existing ignore policy. Returned `reference_json_bytes=0` describes the native result; preparation still opened one reference body.

This validates one controlled cached metadata-absence case with live native data. The error condition was injected rather than observed as a natural archive outage. The prepared cache's source generation does not establish the generation of the fallback native object. Other cached failure modes, products, domains, and analysis t0 were not exercised by this live case.

## 6. USGS and geographic reach resolution

### 6.1 RouteLink

The validated NWM v3.1.6 RouteLink dataset contains:

- 2,776,734 unique NWM feature IDs.
- 8,735 gage-associated reaches.
- A verified association between USGS station `08165500` and NWM feature ID `3586192`.

Dataset provenance:

- Source repository: `jameshalgren/troute-lab`
- Source revision: `bb24900e3229851f6e997b037c337a8643471562`
- Dataset: `RouteLink_CONUS.nc`
- File size: 269,369,766 bytes
- SHA-256: `4957655896f4f27854f893d02fa084f9f79c1cf8e80ce77565a7356dadb6fc0e`

USGS identifiers are preserved as strings, including leading zeros. Ambiguous associations, invalid feature IDs, and duplicate selections are rejected.

### 6.2 Geographic hydrofabric

The validated NWM v3 CONUS channel hydrofabric uses EPSG:4269, while geographic input coordinates use EPSG:4326. Point-to-channel distances are calculated in EPSG:5070.

Dataset source:

`https://www.nohrsc.noaa.gov/owp_files/nwm/data_tools/NWM_channel_hydrofabric.tar.gz`

Published SHA-256:

`77d8975b543ff864cdac0736cc4f455fe86d77049c4d8b1fb8e458ec755dbc94`

### 6.3 Real-data selection results

| Selection method | Result |
|---|---|
| Point near USGS 08165500 | Feature ID 3586192 |
| Point-to-channel distance | Approximately 98.34 m |
| Geographic bounding box | 19 unique reaches |
| GeoJSON polygon | 19 unique reaches |

Reference bounding box:

- West: -99.35
- South: 30.05
- East: -99.30
- North: 30.09

An earlier independent geographic subset comparison returned 18 bounding-box reaches and 12 polygon reaches. These results came from a different validation stage and should not be treated as identical test configurations.

The earlier CLI geographic tests used real hydrofabric data with remote NWM retrieval mocked. They established selection behavior. The subsequent live point, bounding-box, and polygon retrieval and export checks are recorded in Section 6.5.

### 6.4 Geographic limitations

Geographic selection currently targets CONUS.

The nearest channel may not represent the intended hydrologic reach, especially near confluences or parallel channels.

The default limit of 100 reaches for bounding-box and polygon requests is a safeguard, not a measured performance threshold.

Compatibility with historical NWM hydrofabric and RouteLink versions remains under investigation.

### 6.5 Live geographic retrieval and export

- Execution UTC: `2026-11-10T00:48:22.736861+00:00`.
- Implementation commit: `55c2ab571393429cadb9cf801f89bd5da9493af0`.
- Environment: Python `3.14.6`, pandas `3.0.6`, pyarrow `26.0.1`.
- Configuration: `2026-04-19`, cycle `00`, `short_range`, `conus`, lead `f001`, `--no-t0`, reference cache disabled.

The production `streamflow_getter.cli.main` entry point performed real selection, retrieval, and export separately for a point, bounding box, and newly constructed rectangular GeoJSON polygon. The polygon used the same bounds as the box. No geographic or retrieval functions were mocked in this experiment.

Inputs:

- Hydrofabric: `/Users/gonzalo/Documents/troute-lab/data/NWM_v3_hydrofabric.gdb`; layer `nwm_reaches_conus`; CRS verified as `EPSG:4269`.
- Point in longitude/latitude order: `(-99.3217121935161, 30.0699307434853)`; search radius `500 m`.
- Bounding box in west/south/east/north order: `(-99.35, 30.05, -99.30, 30.09)`.
- Polygon ring: `[[-99.35, 30.05], [-99.30, 30.05], [-99.30, 30.09], [-99.35, 30.09], [-99.35, 30.05]]`.

The point selected feature ID `3586192` at a reported distance of `98.34 m`. Both area selections returned exactly these 19 unique IDs, matching the previously recorded bounding-box selection:

```text
3585578, 3585604, 3585606, 3585614, 3585616,
3585620, 3585622, 3585750, 3585754, 3585756,
3586192, 3586194, 3586210, 3586216, 3586218,
3586224, 3586226, 3586228, 3586230
```

| Selection | Format | Rows | Method | Zero-flow rows | Elapsed time |
|---|---|---:|---|---:|---:|
| Point | CSV | 1 | `kerchunk` | 0 | 2.336 s |
| Bounding box | CSV | 19 | `kerchunk` | 4 | 1.068 s |
| Rectangular polygon | Parquet | 19 | `kerchunk` | 4 | 1.104 s |

Elapsed times cover each full CLI call, including geographic selection, retrieval, and export. These single-pass measurements are acceptance-run context, not controlled reader benchmarks.

The matching CIROH reference object was:

`s3://ciroh-nwm-zarr-copy/national-water-model/nwm.20260419/short_range/nwm.t00z.short_range.channel_rt.f001.conus.nc.json`

The exported files were read back and checked for the expected columns, exact reach coverage, forecast metadata, finite discharge, reference time `2026-04-19T00:00:00Z`, and valid time `2026-04-19T01:00:00Z`.

The point CSV value was `0.4099999908357858 m3/s` and agreed with the archived native-download comparison from Section 3.7. Both area outputs ranged from `0` to `0.4399999901652336 m3/s`, preserving four genuine zeros each. The maximum bbox-CSV/polygon-Parquet difference was `8.326672684688674e-17 m3/s`. All three selections agreed at reach `3586192` within `rtol=1e-6` and `atol=1e-6`.

These local generated artifacts under `benchmarks/results/` are covered by the existing Git ignore policy:

| File | Rows | Bytes | SHA-256 |
|---|---:|---:|---|
| `live_geo_20260419_t00_f001_point.csv` | 1 | 243 | `ebce7115eb906db7f2eb8b7f57ba4f071b3adb284941ab4e39a2397383da4dcc` |
| `live_geo_20260419_t00_f001_bbox.csv` | 19 | 2,519 | `fa96b0d8639ec21d5e23f413c5ee4b4518a3c6ca294ce02fc93820d5814660b3` |
| `live_geo_20260419_t00_f001_polygon.parquet` | 19 | 6,625 | `888643c34f1a6a64a5fb4861d7bb7ceb83e275a3540ceb4337b94c841e46d1d7` |

This establishes live CLI geographic selection, Kerchunk retrieval, and CSV/Parquet export for one point and one rectangular region at one forecast cycle and lead. Broader geography, historical network compatibility, analysis t0, and native fallback are outside this experiment. The separate controlled fallback result is recorded in Section 5.4.

## 7. Historical NWM compatibility

### 7.1 Historical Kerchunk and native NetCDF agreement

The production operational reader was tested on selected historical NWM files using the same feature ID, `3586192`.

All comparisons below used CONUS, cycle 00 UTC, and the specified forecast lead.

| Date | Product | Lead | Kerchunk (m³/s) | Native (m³/s) | Absolute difference |
|---|---|---|---:|---:|---:|
| 2019-01-01 | short_range | f001 | 2.699999939650297 | 2.699999939650297 | 0 |
| 2022-01-01 | medium_range_mem1 | f001 | 0.9299999792128801 | 0.9299999792128801 | 0 |
| 2024-01-01 | short_range | f001 | 0.8799999803304672 | 0.8799999803304672 | 0 |
| 2019-01-01 | long_range_mem1 | f006 | 3.519999921321869 | 3.519999921321869 | 0 |
| 2022-01-01 | long_range_mem1 | f006 | 0.5999999865889549 | 0.5999999865889549 | 0 |
| 2024-01-01 | long_range_mem1 | f006 | 0.6299999859184027 | 0.6299999859184027 | 0 |

All six comparisons returned matching forecast valid and reference times.

This supports numerical agreement for the sampled files, not comprehensive compatibility across all historical NWM configurations.

### 7.2 Historical medium-range forecast schedule

CIROH reference inventories indicate a transition in medium-range ensemble forecast frequency between the April 20, 2021, 06 UTC and 12 UTC cycles.

| Initialization | Lead interval | Member 1 | Members 2–6 |
|---|---|---|---|
| Through 2021-04-20 06 UTC | 3 hours | f003–f240 | f003–f204 |
| From 2021-04-20 12 UTC | 1 hour | f001–f240 | f001–f204 |

The production forecast configuration now selects the appropriate lead schedule using the initialization date and cycle.

Real-data testing covered medium-range members 1 and 2 at 06 UTC and 12 UTC on April 20, 2021. Sixteen records were retrieved successfully.

The transition was inferred from sampled archive references, not independently confirmed from an authoritative NOAA release-history record.

### 7.3 Historical feature-ID sets

Complete feature-ID arrays were compared for CONUS short-range, cycle 00 UTC, lead f001.

| Date | Feature count | Data type |
|---|---:|---|
| 2019-01-01 | 2,729,077 | int32 |
| 2022-01-01 | 2,776,738 | int32 |
| 2024-01-01 | 2,776,734 | int64 |

| Comparison | Removed IDs | Added IDs | Identical ordering |
|---|---:|---:|---|
| 2019 → 2022 | 525 | 48,186 | No |
| 2022 → 2024 | 4 | 0 | No |
| 2019 → 2024 | 525 | 48,182 | No |

The four identifiers present in the 2022 sample but absent from 2024 were `4800002`, `4800004`, `4800006`, and `4800007`.

Of the 2,729,077 feature IDs in the 2019 sample, 2,728,552 (approximately 99.98%) were also present in 2024.

The production extractor resolves channels by feature ID rather than assuming fixed array positions. These findings do not independently justify a change to that implementation.

### 7.4 RouteLink v3.1.6 historical compatibility

The modern RouteLink identifier set was compared with the historical operational feature-ID arrays.

| Historical sample | RouteLink IDs absent from NWM | NWM IDs absent from RouteLink | Modern gage reaches absent | Exact set match |
|---|---:|---:|---:|---|
| 2019-01-01 | 48,182 | 525 | 347 | No |
| 2022-01-01 | 0 | 4 | 0 | No |
| 2024-01-01 | 0 | 0 | 0 | Yes |

For the 2019 sample, 8,388 of 8,735 modern gage-associated reaches were present, approximately 96.03%.

The 2024 operational feature-ID set matched RouteLink v3.1.6 exactly.

**Important:** identifier-set equality does not prove unchanged channel geometry, network connectivity, or USGS gage associations.

The existing RouteLink resolver should be retained. Historical version-specific gage-to-reach mapping requires authoritative metadata before automatic remapping is considered.

Existing network comparison work in `troute-lab/repro/network_stats/analyze.py` addresses network outlets and network-size differences. It does not directly establish historical USGS gage-to-feature associations.

### 7.5 Historical source coverage

| Source | Observed coverage evidence | Limitation |
|---|---|---|
| NOAA Google Cloud Storage | Successful native retrieval on sampled dates in 2019, 2022, 2024, and 2026 | Continuous availability not established |
| CIROH S3 Kerchunk | References discovered on sampled dates from 2018 through 2026 | Complete product coverage not established |
| NOAA S3 `noaa-nwm-pds` | Selected paths found in 2025 and 2026 | Earliest available date unverified |
| NOAA S3 before 2025 | Selected paths checked without success | Does not prove complete historical absence |

Historical source discovery, successful file retrieval, and continuous archive coverage are separate levels of evidence.

No authoritative continuous start and end dates have been established for every product, cycle, lead, ensemble member, or domain.

## 8. End-to-end USGS-to-Parquet validation

### 8.1 Configuration

| Parameter | Value |
|---|---|
| Forecast date | 2026-04-19 |
| Product | short_range |
| Cycle | 00 UTC |
| Domain | CONUS |
| USGS station | 08165500 |
| NWM feature ID | 3586192 |
| RouteLink | v3.1.6 |
| Forecast leads | f001–f002 |
| Analysis t0 | Enabled |
| Output | Parquet |

### 8.2 Retrieved records

| Product | Lead | Valid time (UTC) | Streamflow (m³/s) | Method |
|---|---:|---|---:|---|
| analysis_assim | 0 | 2026-04-19 00:00 | 0.41 | Kerchunk |
| short_range | 1 | 2026-04-19 01:00 | 0.41 | Kerchunk |
| short_range | 2 | 2026-04-19 02:00 | 0.40 | Kerchunk |

All three records used feature ID `3586192`.

The analysis t0 source reference time was April 18, 2026, 21:00 UTC, while its valid time matched the forecast initialization at April 19, 2026, 00:00 UTC.

Validation confirmed:

- Successful installed CLI execution.
- Correct USGS-to-RouteLink resolution.
- Three successful Kerchunk retrievals.
- Parquet output with ten expected columns.
- No missing values or duplicate records.
- 123 focused integration tests passed.

Native fallback was not exercised in this end-to-end run.

The result validates one station, one forecast date, one cycle, and two forecast leads.

## 9. Scientific and technical limitations

### 9.1 Retrieval performance

Network and cache conditions were not fully controlled. Accounted HTTP bytes exclude some protocol overhead. Benchmark timings do not include reach resolution.

Additional repeated trials across dates, cycles, reaches, and network conditions are required before making general performance claims.

### 9.2 Source compatibility

A structurally valid Kerchunk reference does not independently establish source-generation equivalence.

Historical product availability varies. A successful sample retrieval does not prove continuous archive coverage.

### 9.3 Network compatibility

Historical feature-ID sets are not identical. Feature-ID persistence does not prove geometric or topological equivalence.

Version-specific RouteLink metadata is needed to validate historical USGS-to-reach associations.

### 9.4 Forecast initialization

The long-range shared `analysis_assim` t0 follows the project roadmap, but its interpretation as the internal initialization of each ensemble member is not scientifically established.

### 9.5 Spatial selection

The nearest channel is not necessarily the hydrologically correct channel. Section 6.5 establishes one live point and rectangular-region case; broader geographic coverage and hydrologic matching remain outside that acceptance result.

### 9.6 Scope

The implemented operational geographic workflow targets CONUS. Full forecast horizons, historical dates, additional domains, and all ensemble combinations have not been exhaustively validated.

## 10. Remaining research priorities

1. Establish systematically verified historical source availability boundaries by product, cycle, lead, and domain.
2. Validate historical RouteLink associations using appropriate version-specific datasets.
3. Expand Kerchunk/native comparisons across additional historical configurations.
4. Repeat performance experiments under controlled network and cache conditions.
5. Validate complete medium- and long-range forecast horizons.
6. Investigate long-range ensemble initialization and shared t0 interpretation.
7. Extend geographic validation beyond the accepted point and rectangular-region case where required by the agreed release scope.
8. Extend domain coverage only when explicitly authorized and technically validated.

Further NWM retrospective and GEOGLOWS development must follow the consultation and coordination requirements in [the project roadmap](../docs/ROADMAP.md).

## 11. Reproducibility and development practices

The benchmark implementations, tests, and experimental summaries are maintained in the repository. Generated result files remain local under the existing Git ignore policy; accepted artifacts are identified by their recorded SHA-256 fingerprints.

- [Benchmark instructions](README.md)
- [Operational NWM guide](../docs/OPERATIONAL_NWM.md)
- [Project roadmap](../docs/ROADMAP.md)
- [Main project README](../README.md)

Historical experiment notes and milestone-by-milestone development records remain recoverable through Git history, including commit `1f0d795`.

This report is a consolidated account of documented validation evidence. It does not replace the original experimental outputs or imply that untested combinations have been verified.

Development should continue through focused changes, reusable production modules, automated regression tests, and reviewable Git commits.


## Operational NWM version provenance and RouteLink compatibility — November 11, 2026

### Objective

Close the roadmap requirement to handle operational NWM model-version
changes without changing the existing Kerchunk/native source-path logic,
and prevent USGS-gage resolution from silently using a known incompatible
RouteLink crosswalk.

### Operational model-version provenance

Model version is derived from forecast initialization time rather than
selected manually for operational retrieval. The verified transition
registry used by the implementation is:

- NWM 1.1 at the project baseline of 2018-01-01 00Z.
- NWM 1.2 from 2018-03-06 12Z.
- NWM 2.0 from 2019-06-19 12Z.
- NWM 2.1 from 2021-04-20 12Z.
- NWM 3.0 from 2023-09-20 12Z.
- NWM 3.1 from 2026-08-18 12Z.

Initializations before the 2018 project baseline remain unresolved rather
than being assigned a guessed version.

Operational run manifests now retain the derived version for every planned
configuration and summarize all resolved versions used by the request.

### Live transition validation

One strict request was validated across the NWM 3.0 to 3.1 transition on
2026-08-18 using the unchanged operational source-path logic:

- 11Z initialization -> NWM 3.0.
- 12Z initialization -> NWM 3.1.
- Same reach: 3586192.
- Lead: f001.
- Both results used Kerchunk.
- Kerchunk/native absolute difference at 11Z: 0.0 m3/s.
- Kerchunk/native absolute difference at 12Z: 0.0 m3/s.
- One manifest retained both model versions.

### RouteLink crosswalk version evidence

Published NWM 3.0.17 and 3.1.6 CONUS RouteLink crosswalks were compared
exhaustively. The transition reproduced the independently documented
crosswalk changes:

- 80 gages added in 3.1.
- 5 gages removed from 3.0.
- 488 common gages moved to different NWM features.

Canonical complete-crosswalk SHA-256 fingerprints:

- NWM 3.0: `3e4232517ce3958bebfa7d9d66826f8ee59c34f0b5b90fb540c3d4ab159d2c68`
- NWM 3.1: `c0ee33504fd74319e68ba07b370110d022efe09a76a022ccb7361921fc909ec6`

The local RouteLink used for validation contains 8,735 gages and is an
exact complete-crosswalk match to the published NWM 3.1.6 mapping.

The classifier hashes the complete validated gage-to-feature mapping, not
the NetCDF bytes, filename, metadata timestamp, or selected example gages.

### Compatibility policy

For `--gage` requests:

- known matching request/RouteLink versions are allowed;
- known mismatches are rejected before remote NWM retrieval;
- a request spanning incompatible known network versions is rejected when
  one version-specific RouteLink is supplied;
- unknown RouteLink fingerprints remain allowed for backward
  compatibility but are recorded explicitly as unknown.

The run manifest records requested gages, resolved NWM feature IDs,
RouteLink filename, canonical crosswalk hash, classified network version,
gage count, compatibility status, and requested NWM versions.

### Final live acceptance

Real RouteLink:

`troute-lab/repro/network_stats/data/RouteLink_CONUS.nc`

Compatible request:

- initialization: 2026-11-10 00Z;
- derived NWM version: 3.1;
- USGS gage: 07166500;
- resolved NWM feature: 20955128;
- RouteLink version: 3.1;
- RouteLink canonical SHA-256: `c0ee33504fd74319e68ba07b370110d022efe09a76a022ccb7361921fc909ec6`;
- retrieval method: Kerchunk;
- CLI streamflow: 0.9399999789893628 m3/s;
- direct native NetCDF: 0.9399999789893627 m3/s;
- absolute difference: 1.1102230246251565e-16 m3/s.

Acceptance artifacts:

- `benchmarks/results/live_gage_routelink_v31_20261110_t00_f001.csv`
  - rows: 1
  - bytes: 243
  - SHA-256: `fa0efeb1b108b8c944c5253bab8ab98f81bb91a89346a316db73af0925fa19ca`
- `benchmarks/results/live_gage_routelink_v31_20261110_t00_f001.csv.manifest.json`
  - bytes: 2607
  - SHA-256: `ea3c40526b146706fb0959ee4894c9f6a1602aa75e4365450967a1de5b9f96db`

Historical protection was validated with the same real RouteLink and an
operational request initialized at 2026-04-19 00Z:

- requested NWM version: 3.0;
- RouteLink version: 3.1;
- result: rejected as incompatible;
- remote operational retrieval calls: 0;
- output CSV created: no;
- run manifest created: no.

### Automated validation

Final pre-documentation repository suite after implementation:

- 103 operational CLI tests passed.
- 165 focused version/RouteLink/provenance tests passed.
- 815 full repository tests passed.
- `git diff --check` passed.

### Remaining scope

RouteLink compatibility is established for USGS `--gage` resolution.
This evidence does not establish exact version identity for hydrofabric
geometry used by `--point`, `--bbox`, or `--polygon`. Geographic
hydrofabric-version compatibility remains a separate validation task.


## Operational source-availability boundaries — November 12, 2026

### Objective

Resolve the roadmap requirement to document operational data date ranges
by source and product without inferring archive continuity from isolated
successful retrievals.

### Method

Two read-only metadata audits were run against the source paths generated
by the production operational configuration.

H1B sampled all 13 currently supported CONUS forecast products across 12
dates from September 2018 through November 2026. Each row checked:

- NOAA Google Cloud Storage native NetCDF;
- CIROH Kerchunk reference storage;
- NOAA `noaa-nwm-pds` S3.

Representative leads were selected according to the current product
schedules:

- short range: f001;
- medium range: f003;
- long range: f006.

H1C2 then refined transitions at valid initialization-cycle resolution.
GCS and CIROH were required to agree at each tested initialization.

### Verified current-path boundaries

| Product family | Previous valid initialization | First observed available initialization | Representative lead | NWM version at boundary |
|---|---|---|---:|---|
| Short range | 2018-09-16 23Z | **2018-09-17 00Z** | f001 | 1.2 |
| Long-range members 1–4 | 2018-09-16 18Z | **2018-09-17 00Z** | f006 | 1.2 |
| Medium-range members 1–6 | 2019-06-19 06Z | **2019-06-19 12Z** | f003 | 2.0 |
| Medium-range no-DA | 2021-04-20 06Z | **2021-04-20 12Z** | f003 | 2.1 |
| Medium-range blend | 2023-09-19 00Z | **2023-09-19 06Z** | f003 | 2.1 |

GCS native and CIROH Kerchunk paths had identical status at these tested
boundaries.

The six medium-range ensemble paths align exactly with the registered NWM
2.0 transition. The no-DA path aligns exactly with NWM 2.1.

The medium-range blend path does **not** align with the NWM 3.0 transition:
it is present from 2023-09-19 06Z while the registered NWM 3.0 transition
is 2023-09-20 12Z. No causal version-transition claim is made for blend.

### NOAA S3

All 13 tested current product paths had the same observed NOAA
`noaa-nwm-pds` transition:

- final valid initialization on 2024-12-31: missing;
- 2025-01-01 00Z: present.

For short range the immediately preceding valid initialization was 23Z.
For the tested medium- and long-range products it was 18Z.

### Evidence artifacts

`benchmarks/results/h1b_source_availability_matrix.csv`

- rows: 156
- bytes: 90,127
- SHA-256: `45e61c3edb7afddb4e38fcf80ad5fc2294cda6b961d2706abe535598a12e3ca3`
- metadata/probe errors: 0

`benchmarks/results/h1c_exact_initialization_boundaries.csv`

- rows: 488
- bytes: 97,600
- SHA-256: `e31d3de9676a2e9bac3699957337ee1642d21696a76313c85d66b581ffe63bbe`
- repository source changes during audit: none

Both artifacts remain generated local evidence under the existing ignore
policy.

### Interpretation and limitations

These are boundaries for the **current streamflow_getter source-path
conventions and representative valid leads**.

A missing current path does not prove that a differently named historical
product, file layout, or archive object did not exist.

The broad matrix plus exact transition windows substantially improve the
archive evidence, but they do not constitute an exhaustive check of every
forecast initialization after each boundary. Continuous gap-free coverage
therefore remains a stronger claim than this audit supports.

No production retrieval code changed during H1B or H1C2.
