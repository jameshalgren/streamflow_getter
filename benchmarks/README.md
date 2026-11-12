# NWM Operational Retrieval Benchmarks

## 1. Purpose

This directory contains experimental work supporting the operational National Water Model (NWM) retrieval requirements defined in `docs/ROADMAP.md`.

The objectives are to:

- Compare Kerchunk and native NetCDF retrieval performance.
- Measure elapsed time and accounted network data transfers.
- Verify numerical agreement and forecast timestamps.
- Evaluate multi-reach retrieval and reference caching.
- Provide reproducible evidence for future operational implementation.

These benchmarks provide reproducible validation of operational NWM retrieval methods. Changes to production behavior are validated separately through the test suite.

## 2. Reference Dataset

| Parameter | Configuration |
|---|---|
| Forecast date | 2026-04-19 |
| Product | `short_range` |
| Cycle | `t00z` |
| Domain | CONUS |
| Variable | `streamflow` |
| Units | m³/s |
| Tested forecast hours | `f001`–`f006` |
| Available forecast hours | `f001`–`f018` |
| Available cycles | 24 hourly cycles |
| Features per file | 2,776,734 |

The initial benchmark used one reach across six forecast hours. Multi-reach extraction has subsequently been validated for five reaches.

## 3. Retrieval Methods

The benchmark compares four methods:

| Method | Description |
|---|---|
| `kerchunk` | Remote NetCDF access through CIROH Kerchunk references |
| `native_remote` | Native NetCDF access through HTTP range requests |
| `native_download` | Download complete NetCDF file and read locally |
| `native_local` | Read an existing local NetCDF file |

All four methods support the tested multi-reach benchmark workflow.

Performance measurements represent individual retrieval operations, not separate network transfers for each reach.

Accounted response-body bytes do not include all HTTP metadata requests or protocol overhead.

## 4. Project Files

| File | Purpose |
|---|---|
| `repeated_benchmark.py` | Main benchmark runner with single- and multi-reach support |
| `test_repeated_benchmark.py` | Benchmark regression tests |
| `http_trace.py` | HTTP read instrumentation |
| `compare_nwm_access.py` | Initial retrieval comparison |
| `cache_experiment.py` | Same-process and separate-process retrieval experiments |
| `reference_cache_experiment.py` | Reference-cache performance experiments |
| `live_cache_integration.py` | Live cache integration verification |
| `test_reference_validation.py` | Reference-validation tests |
| `test_reference_cache.py` | Cache loading and recovery tests |
| `test_cache_manifest.py` | Cache integrity and persistence tests |
| `test_cache_freshness.py` | Metadata freshness tests |

Reference caching and validation are implemented in `src/streamflow_getter/reference_cache.py` and `src/streamflow_getter/reference_validation.py`. The benchmark tests exercise these production modules.

## 5. Environment and Dependencies

Use the repository's `uv`-managed Python environment.

The benchmark uses NumPy, xarray, fsspec, s3fs, and Zarr. Native NetCDF experiments additionally require `h5py` and `h5netcdf`.

Run the benchmark with these optional dependencies:

```bash
uv run --locked --with h5py --with h5netcdf \
  python benchmarks/repeated_benchmark.py --help
```

## 6. Running the Benchmark

### Single-reach benchmark

```bash
uv run --locked --with h5py --with h5netcdf \
  python benchmarks/repeated_benchmark.py \
  --start-hour 1 \
  --end-hour 6 \
  --trials 5 \
  --reach 3586192
```

### Multi-reach benchmark

```bash
uv run --locked --with h5py --with h5netcdf \
  python benchmarks/repeated_benchmark.py \
  --start-hour 1 \
  --end-hour 1 \
  --trials 1 \
  --reaches 1122645 3586192 7144704 14191043 23610484
```

Both commands use the April 19, 2026, `t00z` short-range CONUS forecast.

The benchmark supports forecast hours `f001`–`f018`, configurable forecast dates and cycles, and automated multi-day execution using `--start-date` and `--end-date`. A complete 18-hour cycle and a three-day benchmark have been validated.

Reach indices are resolved and verified before timed retrievals.

## 7. Benchmark Outputs

The benchmark writes two CSV files under `benchmarks/results/`.

**Operation-level results**

`repeated_benchmark.csv`

Contains one record per retrieval operation, including:

- Trial, forecast hour, and retrieval method
- Number of reaches
- Elapsed time
- Instrumented HTTP read count
- Accounted response-body bytes
- Reference JSON bytes

**Reach-level results**

`repeated_benchmark_flows.csv`

Contains one record per reach and retrieval method, including:

- Trial and forecast hour
- Retrieval method and feature ID
- Streamflow in m³/s
- Forecast valid time
- Forecast reference time

Separating these outputs prevents network-transfer measurements from being counted repeatedly for each reach.

The runner refuses to overwrite existing output CSVs. Use a new `--output-prefix` for a deliberate new experiment and preserve accepted results. Record their configuration and SHA-256 fingerprints in `PROGRESS.md`.

## 8. Automated Testing

Run the complete test suite:

```bash
uv sync --locked --extra operational --extra spatial --extra parquet
uv run --locked --extra operational --extra spatial --extra parquet pytest -q -ra
```

The full repository suite exercises optional operational, spatial, and Parquet capabilities. For the latest verified environment, test result, and CI status, see [Development Status](../docs/DEVELOPMENT_STATUS.md).

The benchmark tests verify batch extraction, feature identity, reach ordering, single-reach compatibility, non-finite value rejection, CSV output structure, streamflow disagreement detection, and timestamp disagreement detection.

Tests using simulated retrieval methods do not require network access.

## 9. Reference Cache

The production reference cache supports:

- Kerchunk reference structure and source validation
- External byte-range validation
- Metadata comparison using ETag and GCS generation
- SHA-256 integrity verification
- Atomic single-record persistence
- Failed-refresh protection
- Disk-cache reuse across separate executions

The cache stores reference metadata, not the complete NWM model data. Remote model-data chunks are still retrieved when required.

Remote reference/source compatibility and concurrent cache refresh remain unresolved operational concerns.

See the [single-reference and batch preparation guide](../docs/OPERATIONAL_NWM.md#preparing-a-reference-before-retrieval) for API usage. Live preparation/retrieval and batch-reuse evidence, including artifact fingerprints and limitations, is recorded in [PROGRESS Section 4.4](PROGRESS.md#44-live-preparation-followed-by-cached-retrieval) and [Section 4.5](PROGRESS.md#45-live-batch-preparation-and-reuse).

## 10. Remaining Validation and Research

The following capabilities have been implemented:

- Multi-reach retrieval and full 18-hour short-range benchmarking.
- Kerchunk-first operational retrieval with native NetCDF fallback.
- Reference caching and integrity validation.
- Single-reference and batch preparation with complete request validation and source deduplication.
- USGS gage resolution using RouteLink.
- Geographic point, bounding-box, and polygon selection.
- Short-, medium-, and long-range operational product configurations.
- Analysis t0 integration and CSV/Parquet output.
- Selected historical Kerchunk/native NetCDF comparisons.

Selected live acceptance evidence is recorded in [PROGRESS Section 6.5](PROGRESS.md#65-live-geographic-retrieval-and-export) for geographic CLI retrieval/export and [Section 5.4](PROGRESS.md#54-controlled-native-fallback-integration) for controlled missing-reference injection with real native retrieval. Both cases use April 19, 2026, cycle 00, short-range CONUS f001. Their scope and artifact fingerprints are recorded there.

Remaining research priorities include:

- Controlled performance measurements across additional dates and cycles.
- Continuous historical source-availability verification.
- Version-specific RouteLink and NWM network compatibility.
- Complete medium- and long-range forecast-horizon validation.
- Scientific assessment of long-range ensemble initialization.
- Geographic validation beyond the accepted point and rectangular-region case.
- Additional NWM domains where explicitly authorized.

See [PROGRESS.md](PROGRESS.md) for experimental evidence, numerical results, and scientific limitations.

Further NWM retrospective and GEOGLOWS development must follow the consultation requirements in [the project roadmap](../docs/ROADMAP.md).

## 11. Development Practices

- Reuse existing implementations before introducing new functions.
- Keep experimental code organized and avoid redundant scripts.
- Maintain automated regression coverage.
- Do not commit downloaded NetCDF files.
- Avoid unnecessary backups and temporary copies.
- Use Git for version history.
- Keep changes on the development branch.
- Keep pull requests focused, validate changes before publishing, and record their limitations.

## 12. Experiment History

See [`PROGRESS.md`](PROGRESS.md) for verified measurements, completed milestones, scientific limitations, and the next development objectives.
