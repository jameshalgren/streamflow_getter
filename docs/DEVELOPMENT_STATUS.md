# Development Status — NWM Implementation Checkpoint

**Checkpoint date:** November 7, 2026
**Updated:** November 12, 2026 (America/Chicago)
**Branch:** `research/nwm-historical-coverage`
**Status:** Operational NWM backend remains published in PR #6. Reference/cache reliability, request planning, strict run provenance, operational model/RouteLink compatibility, and current CONUS source-path availability boundaries are validated on the active PR branch. Named-event CLI exposure and later research-source integration remain separate work.

## 1. Completed Work

- Implemented operational NWM forecast retrieval across supported CONUS short-, medium-, and long-range products.
- Preserved retrospective NWM retrieval for versions 2.1 and 3.0.
- Implemented Kerchunk-first retrieval with native NetCDF fallback under supported conditions.
- Added optional reference caching with integrity and source validation.
- Added shared single-reference preparation and batch preparation with request validation and source deduplication.
- Implemented reach selection using NWM feature IDs, USGS gages, geographic points, bounding boxes, and polygons.
- Added analysis timestep (`t0`) handling, forecast metadata, and CSV/Parquet output.
- Consolidated production modules, tests, benchmarks, and documentation.
- Integrated upstream's `research-plan.md` without modifying the original `docs/ROADMAP.md`.

## 2. Verification Completed

### Original checkpoint — November 7, 2026 (`dbc5a27`)

- 638 automated tests passed.
- Python package import and CLI commands verified.
- Wheel and source distribution built successfully.
- Wheel installation and CLI execution verified in an isolated environment.
- Git formatting checks passed.
- Working tree clean at the checkpoint.
- Historical coverage, source agreement, reference caching, and retrieval performance documented in `benchmarks/PROGRESS.md`.

These checks validate the tested software behavior and selected research cases; they do not establish complete scientific validation of every NWM product or historical period.

### CI dependency correction — November 9, 2026

- Updated the CI workflow to install the `operational`, `spatial`, and `parquet` extras, using `--locked` for synchronization and execution.
- Local environment: macOS ARM64, Python 3.14.6, uv 0.13.4.
- Full test suite result: **638 passed in 1.90 seconds**.
- `git diff --check` passed; `pyproject.toml` and `uv.lock` were unchanged.

Validated commands:

    uv sync --locked --extra operational --extra spatial --extra parquet
    uv run --locked --extra operational --extra spatial --extra parquet pytest -q -ra

This is local validation. Verify the GitHub Actions result for the updated PR head after pushing the commit.

### Live geographic retrieval and controlled fallback — November 9, 2026

At implementation commit `55c2ab571393429cadb9cf801f89bd5da9493af0`:

- Live production CLI retrieval passed for a point CSV, bounding-box CSV, and equivalent rectangular-polygon Parquet: 1, 19, and 19 rows, all through Kerchunk. See [PROGRESS Section 6.5](../benchmarks/PROGRESS.md#65-live-geographic-retrieval-and-export).
- Controlled missing-reference injection led the production coordinator to retrieve real native NetCDF data for reach `3586192`. Method, fallback reason, metadata, timestamps, and numerical agreement with the accepted point records passed. See [PROGRESS Section 5.4](../benchmarks/PROGRESS.md#54-controlled-native-fallback-integration).

These local acceptance cases cover April 19, 2026, cycle 00, short-range CONUS f001 with reference caching disabled. Exact UTC execution times, configurations, limitations, and artifact fingerprints are recorded in the linked sections. Full-suite results and hosted-CI verification are tracked separately in this section.

### Local cache I/O correction — recorded November 10, 2026

Validated the correction in a working tree based on `2aca2e78a455c63139f9924b22931c66e0ab2cf3`.

- `load_cache_record` preserves recovery for missing or invalid cached records and propagates other local filesystem errors.
- Three regression cases cover `PermissionError`, `IsADirectoryError`, and `OSError` with `errno.EIO`. They verify that the same exception propagates, the reference-body downloader is not called, and existing cache bytes remain unchanged.
- Local environment: macOS ARM64, Python 3.14.6, pytest 9.1.1.
- Locked full-suite result: **641 passed in 1.90 seconds**.
- `git diff --check` passed; `pyproject.toml`, `uv.lock`, and `docs/ROADMAP.md` were unchanged.

Validated command:

    uv run --locked --extra operational --extra spatial --extra parquet pytest -q -ra

Remote freshness metadata is still checked before the local cache read. This is local automated validation; verify GitHub Actions for the published PR head.

### Reference preparation and reuse — recorded November 10, 2026

Validated in working trees based on `e857f6987a07fafe7d3781307c528102bf99199d`. The operational-module fingerprints distinguish the intermediate and completed implementations in [PROGRESS Section 4.3](../benchmarks/PROGRESS.md#43-shared-reference-preparation).

- The Kerchunk reader and preparation APIs share source resolution, reference validation, and the existing cache implementation.
- Batch requests are validated before acquisition, follow product-specific lead schedules, include analysis t0 by default, and deduplicate by reference path plus native URL. Results contain compact source summaries; acquisition errors propagate unchanged.
- Local environment: macOS ARM64, Python 3.14.6, pytest 9.1.1.
- Intermediate single-reference implementation (C3): **643 passed in 1.32 seconds**.
- Completed batch implementation (C5): **655 passed in 0.92 seconds**, using the locked full-suite command recorded above.
- Live single-reference preparation followed by production retrieval passed (C4); see [PROGRESS Section 4.4](../benchmarks/PROGRESS.md#44-live-preparation-followed-by-cached-retrieval).
- Live preparation of five unique analysis/forecast references and unchanged warm-cache reuse passed (C6); see [PROGRESS Section 4.5](../benchmarks/PROGRESS.md#45-live-batch-preparation-and-reuse).

The final documentation consolidation preserves the source and test fingerprints validated in C5 and C6. These are local results; verify GitHub Actions for the published PR head separately.

### Remote reference reliability — recorded November 10, 2026

Validated in a local working tree based on `f8dde69cd7fa6bb33a3180a5637b4f3bf0d32e1d`, including the D1-D3 implementation changes. Production and regression-test fingerprints are recorded in [PROGRESS Section 4.6](../benchmarks/PROGRESS.md#46-remote-reference-reliability).

- Missing remote reference metadata or bodies are classified as `RemoteReferenceNotFoundError`, preserving the original cause. Local cache, native-source metadata, authorization, and integrity failures remain distinguishable.
- Fresh reference metadata bypasses stale S3 listings; listing invalidation also prevents a later body open from reusing an outdated size or ETag.
- Cached retrieval permits native fallback only for the classified missing-reference error. Preparation APIs retain their strict failure behavior. When both readers fail, diagnostics retain the native cause and the Kerchunk reason.
- Local environment: macOS ARM64, Python 3.14.6, pytest 9.1.1; s3fs and fsspec 2026.9.0.
- Completed implementation (D3), using the locked full-suite command above: **689 passed in 1.88 seconds**.
- Controlled cached fallback with live native retrieval passed (D4): one CONUS short-range forecast lead and reach, correct timestamps and flow agreement, and the prepared cache record preserved. See [PROGRESS Section 5.5](../benchmarks/PROGRESS.md#55-controlled-cached-native-fallback) for the artifact and bounded scope.

These follow-up changes remain local at this checkpoint. The results do not establish hosted-CI success; verify GitHub Actions for the relevant PR head after publication. This documentation update preserves the validated production and test files.

### Operational CLI cache policy — recorded November 10, 2026

Validated in a working tree based on `b3995ee6b0a1173ec4e3bebb1123ac1c30cfd588`.

- `nwm-operational` uses `~/.cache/streamflow_getter` by default.
- `--cache-dir PATH` selects an explicit persistent reference cache.
- `--no-cache` disables persistent reference caching.
- `--cache-dir` and `--no-cache` are mutually exclusive.
- Lower-level Python retrieval APIs retain their existing explicit `cache_dir=None` semantics.
- Local automated result: **694 passed in 1.20 seconds**.
- A live four-run acceptance case verified default cold creation, default warm reuse without cache-record modification, explicit override, and explicit no-cache behavior. All four runs returned identical short-range f001 streamflow for reach `3586192`.
- See [PROGRESS Section 4.7](../benchmarks/PROGRESS.md#47-operational-cli-cache-policy) for the live artifact and bounded scope.

These changes are separate from the previously published reference-reliability contribution and preserve its fallback/error contract.

### Operational request planning — recorded November 11, 2026

Validated in a working tree based on `c7108c2f835ba23b843cbf22d2e6df30591b0805`.

- Added a pure inclusive UTC date-range planner that reuses `ForecastConfig` validation rather than duplicating product/cycle/domain rules.
- Added deterministic recent-day resolution to absolute UTC dates.
- Added an immutable named-event window abstraction that delegates to the same planner; no event database or duplicate NWM reader was introduced.
- Added strict multi-configuration execution through the existing single-configuration retrieval primitive.
- Shared normal analysis t0 is decoded once per unique resolved analysis source and attached to each requested forecast context; no-DA analysis remains distinct.
- The operational CLI preserves `--date` and adds `--start-date` / `--end-date` and `--recent-days`. The CLI still intentionally exposes one cycle and one product per request.
- Local full-suite result after the completed event abstraction: **746 passed in 0.88 seconds**.
- Live multi-product execution passed with four requested products and only two actual analysis-t0 decodes; see [PROGRESS Section 4.8](../benchmarks/PROGRESS.md#48-operational-request-planning-and-multi-configuration-execution).
- Live April 19-21, 2026 CLI period retrieval returned three distinct initializations and matched the accepted native-download values exactly for the selected f001 reach.

The planner and executor do not create a second retrieval implementation: existing source resolution, Kerchunk/native fallback, reference cache, timestamp validation, reach extraction, and output writing remain authoritative.

### Operational run provenance — recorded November 11, 2026

Validated in a working tree based on `2842ed05c03e4af6f5d9d60c4c2cb75ce6f2154d`.

- Added explicit stable contracts for the established one-product operational row schema and the combined-request schema carrying `requested_product`.
- Preserved actual source `product`, literal `reference_time`, forecast/reference/valid-time identity, and retrieval `method` independently from requested product/member identity.
- Added strict manifest schema version 1 with resolved request, reaches, t0 policy, cache policy, software information, diagnostics, source/method counts, output-contract metadata, and expected-versus-actual completeness.
- Added safe JSON manifest sidecar publication with no-overwrite behavior and in-process rollback of newly created data if sidecar publication fails.
- Integrated run-manifest publication into the operational CLI without adding `requested_product` to the established CSV/Parquet streamflow export.
- Updated the legacy CLI test fixture to emit product-aware and schedule-aware rows so the production provenance validator remains strict.
- Local full-suite result after CLI integration: **780 passed in 1.08 seconds**.
- Live April 19-21, 2026 CLI acceptance produced three exact native-agreement streamflow rows plus a complete strict manifest; see [PROGRESS Section 4.9](../benchmarks/PROGRESS.md#49-stable-operational-output-provenance-and-run-manifests).

The manifest currently represents successful strict runs only. Partial-success/failure manifests are intentionally not inferred from incomplete output.

## 3. Known Limitations and Remaining Work

- Operational CLI reference caching is enabled by default at `~/.cache/streamflow_getter`; users can override the directory or disable persistent caching explicitly. Lower-level Python retrieval APIs retain explicit `cache_dir=None` semantics.
- Explicit date-range and recent-day CLI selection are implemented. Named events are currently a Python planning abstraction and are not exposed by the CLI until request/run provenance can preserve the event name.
- Multi-configuration execution shares decoded analysis t0 rows when requested configurations resolve to the same analysis source. Multi-product/member selection is not yet exposed by the CLI.
- Cached retrieval falls back to native NetCDF only for a classified missing remote reference (`RemoteReferenceNotFoundError`); other cached errors propagate. Controlled live acceptance passed for one reference-metadata absence case. Broader live coverage remains unverified.
- Historical NWM network compatibility requires version-specific verification.
- Complete forecast-horizon and historical product coverage have not been verified.
- Some analysis-to-forecast `t0` relationships require additional scientific review.
- NRDS and GEOGLOWS adapters remain future development work.

**Next backend task:** Audit and design named-event CLI exposure now that request provenance, version compatibility, and operational source-path availability are documented. Do not mix NRDS/Alabama research-source work into this backend unit.

## 4. Next Research Phase — Alabama

`docs/ROADMAP.md` remains the controlling guide. Reconcile the root `research-plan.md` with verified NRDS data and the current upstream contributions before implementing the Alabama comparison. The next design task is to align product/version selection, CLI compatibility, and time and provenance fields with [PR #4](https://github.com/jameshalgren/streamflow_getter/pull/4) and [PR #5](https://github.com/jameshalgren/streamflow_getter/pull/5).

Close the backend gaps in reliability, request planning, and output metadata needed for the pilot before new NRDS implementation. Verify the actual geographic coverage and any version-matched mapping before selecting the pilot.

Planned activities:

1. Review the research plan and confirm data availability, temporal coverage, and spatial identifiers.
2. Reuse suitable version-matched mappings and develop only the NRDS access and matching components required by the verified pilot.
3. Align comparable forecasts, locations, and timestamps.
4. Implement reproducible comparison statistics and tests.
5. Document the methodology, results, assumptions, and limitations.

Continue Alabama work on `research/alabama-nwm-nrds-comparison`; its last recorded checkpoint is `dbc5a27`. Backend corrections and reference-preparation development continue on `research/nwm-historical-coverage`. Website development follows backend acceptance.

## 5. Contribution Status

The NWM implementation has been submitted in [PR #6](https://github.com/jameshalgren/streamflow_getter/pull/6), from `research/nwm-historical-coverage`.

Maintain this existing contribution through focused corrections and validation. The reference-preparation contribution consolidates implementation, regression coverage, and bounded live acceptance evidence. Local validation has passed; GitHub Actions must be checked for the published PR head.

Preserve the original roadmap, keep Git history traceable, and avoid unnecessary dependencies or duplicated implementations.


## November 11, 2026 — Operational version and RouteLink compatibility

Operational NWM retrieval now derives model-version provenance from
forecast initialization time and records it in successful run manifests.

RouteLink-based USGS gage resolution now has content-based network-version
protection. Complete CONUS gage-to-feature crosswalk fingerprints identify
the verified NWM 3.0 and 3.1 mappings:

- NWM 3.0: `3e4232517ce3958bebfa7d9d66826f8ee59c34f0b5b90fb540c3d4ab159d2c68`
- NWM 3.1: `c0ee33504fd74319e68ba07b370110d022efe09a76a022ccb7361921fc909ec6`

Known RouteLink/request mismatches are rejected before remote retrieval.
Unknown RouteLink fingerprints remain usable but are explicitly recorded
as unverified.

Final live validation used gage `07166500` with the local NWM 3.1
RouteLink. It resolved to feature `20955128`, retrieved the 2026-11-10
00Z short-range f001 forecast by Kerchunk, and agreed with direct native
NetCDF to `1.1102230246251565e-16 m3/s`.

A 2026-04-19 00Z NWM 3.0 request using the same NWM 3.1 RouteLink was
rejected before retrieval; the recorded retrieval-call count was zero.

Current validation baseline for this contribution: **815 passing tests**.

Remaining version work is intentionally separate: version compatibility
for hydrofabric geometry used by point, bounding-box, and polygon
selection has not been inferred from the RouteLink result.


## November 12, 2026 — Operational source availability

The current operational source-path boundaries have now been audited
separately from retrieval correctness.

Verified GCS-native/CIROH-Kerchunk boundaries for representative valid
leads:

- `short_range`: 2018-09-17 00Z, f001;
- `long_range_mem1`–`long_range_mem4`: 2018-09-17 00Z, f006;
- `medium_range_mem1`–`medium_range_mem6`: 2019-06-19 12Z, f003;
- `medium_range_no_da`: 2021-04-20 12Z, f003;
- `medium_range_blend`: 2023-09-19 06Z, f003.

The six medium-range members align with the registered NWM 2.0 transition
and no-DA aligns with NWM 2.1. Blend does not align with NWM 3.0 and is
documented without a causal version-transition claim.

All 13 supported current product paths were missing from NOAA
`noaa-nwm-pds` at their final valid initialization on December 31, 2024
and present at 2025-01-01 00Z.

H1B recorded 156 metadata-only matrix rows with zero probe errors.
H1C2 recorded 488 exact-boundary probes.

Evidence fingerprints:

- H1B: `45e61c3edb7afddb4e38fcf80ad5fc2294cda6b961d2706abe535598a12e3ca3`
- H1C2: `e31d3de9676a2e9bac3699957337ee1642d21696a76313c85d66b581ffe63bbe`

These results document current source-path boundaries. They do not prove
that differently named historical files were absent or that every
initialization after each boundary is gap-free.
