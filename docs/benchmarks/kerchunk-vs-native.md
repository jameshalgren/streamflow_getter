# Benchmark: Kerchunk vs native NetCDF (2026-10-28)

Roadmap step 1. Reading `streamflow` for 6 Alabama gaged reaches from the
2026-04-19 t00z forecast (NWM v3.0 files), CONUS `channel_rt`, 8 worker
threads. Repeated on the 2026-10-27 t00z forecast (v3.1 files, which are
chunked differently); see [v3.1 files](#v31-files-2026-10-27). Machine:
Apple M4 Max (12 performance + 4 efficiency cores), 64 GB, macOS 26.7.1, on
Wi-Fi 802.11ax. Measured throughput (12-15 MB/s, about 100-120 Mbit/s) was
well under the Wi-Fi link rate, so upstream bandwidth or per-request latency
was the limit. Script: [`benchmarks/kerchunk_vs_native.py`](../../benchmarks/kerchunk_vs_native.py);
raw rows: [`benchmarks/results/2026-10-28.csv`](../../benchmarks/results/2026-10-28.csv).
Every method returned identical values in every run.

| Method | What it reads |
|---|---|
| `native_full` | whole NetCDF file from `s3://noaa-nwm-pds`, opened in memory |
| `native_range` | h5netcdf over S3 byte ranges (1 MiB readahead blocks) |
| `kerchunk_gcs` | CIROH refs as published (byte ranges on GCS), opened with xarray/zarr |
| `kerchunk_s3` | same refs with URLs rewritten to `s3://noaa-nwm-pds` |
| `kerchunk_direct` | refs used only for offsets: fetch the `streamflow` chunk per file, `feature_id` once, decode with numcodecs |

## Results: v3.0 files, 2026-04-19 (median)

| Product (files) | Method | Seconds | MB read | Requests |
|---|---|---:|---:|---:|
| short_range (18), 3 runs | native_full | 17.5 | 257 | 18 |
| | native_range | 23.7 | 67 | 36 |
| | kerchunk_gcs | 4.4 | 48 | 54 |
| | kerchunk_s3 | 4.8 | 48 | 54 |
| | kerchunk_direct | 5.4 | 37 | 37 |
| medium_range_mem1 (240), 1 run | native_range | 172.5 | 886 | 480 |
| | kerchunk_gcs | 39.9 | 623 | 720 |
| | kerchunk_s3 | 46.9 | 623 | 720 |
| | kerchunk_direct | 31.5 | 478 | 481 |

`native_full` was skipped for medium range (240 x 14 MB = 3.4 GB).
Short-range `kerchunk_direct` ranged 3.9 to 8.1 s across runs; the short
runs are noisy at this size.

## Findings

- **Kerchunk is about 4x faster** than either native path and reads 5x fewer
  bytes than downloading whole files. Kerchunk first is confirmed.
- **There is a hard floor of about 2 MB per file per variable** in v3.0
  files. Each variable in the NetCDF is a single chunk of all 2,776,734 reaches
  (`streamflow` about 2.0 MB compressed, `feature_id` about 0.6 MB). Any
  reader, Kerchunk included, must fetch the whole chunk to get one reach.
  Newer or regenerated references cannot beat this; only re-chunked data
  (for example a Zarr copy chunked along time) could. Re-running the CIROH
  Kerchunk process could still help with freshness or the GCS/AWS pointer.
  See [Tradeoffs](#tradeoffs).
- **`feature_id` is identical across files of a cycle** (same byte layout in
  every ref), so it can be read once: `kerchunk_direct` cuts bytes by 23% and
  was the fastest on the 240-file run. It is the model for the library path.
- **Rewriting refs from GCS to S3 works** (offsets match; values identical),
  so S3 is a usable mirror when GCS is slow or blocked. GCS was slightly
  faster from here.
- **`native_range` is slower than downloading whole files** for short range:
  h5py serialises calls across threads, and HDF5 metadata adds round trips.
  The native fallback should download whole files concurrently (per cycle,
  into the cache) rather than read ranges.
- **Ref freshness**: on 2026-10-28 the newest ref folder was `nwm.20261027`
  while `noaa-nwm-pds` already had `nwm.20261028`. Refs lag about a day, so
  "last few days" requests need the native fallback for the current day.
- **S3 `noaa-nwm-pds` starts at `nwm.20250101`** (666 day folders on
  2026-10-28), confirming the teammate note.
- Throughput was network-bound at roughly 12-15 MB/s. At that rate one day of
  short-range cycles (24 x 18 files) is about a minute via `kerchunk_direct`.

## v3.1 files, 2026-10-27

Operational NWM switched to v3.1 on 2026-08-18 (see
[nwm-notes](../nwm-notes.md#model-versions-operational-conus)). v3.1 files
split `streamflow` into 3 HDF5 chunks of 925,578 reaches (~0.55 MB each) and
`feature_id` into 6 of 462,789. The six test reaches span two `streamflow`
chunks (Little Tallapoosa in one, the other five in the next), so
`kerchunk_direct` reads 2 of 3 chunks per file. `kerchunk_direct` was
updated to read only the chunks that hold the requested reaches; before
that it assumed one chunk per variable.

| Product (files) | Method | Seconds | MB read | Requests |
|---|---|---:|---:|---:|
| short_range (18), 3 runs | native_full | 11.6 | 223 | 18 |
| | native_range | 8.5 | 47 | 36 |
| | kerchunk_gcs | 3.1 | 31 | 162 |
| | kerchunk_s3 | 2.9 | 31 | 162 |
| | kerchunk_direct | 3.4 | 20 | 60 |
| medium_range_mem1 (240), 1 run | native_range | 88.0 | 628 | 480 |
| | kerchunk_gcs | 30.8 | 412 | 2160 |
| | kerchunk_s3 | 24.3 | 412 | 2160 |
| | kerchunk_direct | 19.2 | 265 | 726 |

Same machine and network, same session as the v3.0 run. Differences between
the two tables mix the chunking change with different days and network
conditions; the byte counts are the reliable comparison.

- **Kerchunk still wins**, by less: 2.5x to 4.5x faster than `native_range`,
  3.4x faster than `native_full` on short range.
- **Bytes per file roughly halve**: `kerchunk_direct` reads 1.1 MB per
  short-range file (2 chunks) against 2.1 MB in v3.0. Reaches that all sit in
  one chunk would read ~0.55 MB.
- **`native_range` improved most** (23.7 s to 8.5 s on short range): smaller
  chunks mean fewer bytes behind each HDF5 read. It is now faster than
  downloading whole files, unlike in v3.0.
- **Requests went up** with more chunks (162 vs 54 for the xarray paths),
  since xarray loads all 6 `feature_id` chunks per file. Reading `feature_id`
  once per cycle (`kerchunk_direct`) matters more in v3.1.
- The library reader must handle any number of chunks per variable, and
  check the chunk layout per file rather than per date.

## Tradeoffs

The chunking limit is known; options considered so far:

| Option | Speed | Cost |
|---|---|---|
| CIROH refs as published (current choice) | ~2.5-4.5x faster than native remote | ~1 day lag; per-chunk floor (2 MB in v3.0, ~0.55 MB in v3.1) |
| Native files, remote (download or byte ranges) | slowest measured | no extra infrastructure; needed for the newest day |
| Build Kerchunk refs on the fly | slower than using CIROH refs (adds a metadata scan per file) | no dependency on CIROH refs |
| Re-run the CIROH Kerchunk process | same per-file floor | could address lag or the GCS/AWS pointer text |
| Re-host forecasts with different chunking | could beat the floor for few-reach reads | storage and upkeep for a second copy |
| Download once, read locally | fastest after download | significant local storage |

For now: CIROH refs first, native fallback, and a local cache whose size is
the user's choice.

## Reproduce

```bash
uv sync --group bench
uv run --group bench python benchmarks/kerchunk_vs_native.py --repeat 3 \
    --network "Wi-Fi 802.11ax" --out results.csv
uv run --group bench python benchmarks/kerchunk_vs_native.py --product medium_range_mem1 \
    --methods native_range kerchunk_gcs kerchunk_s3 kerchunk_direct \
    --network "Wi-Fi 802.11ax" --out results.csv
```

Each result row records the machine (detected) and `--network` (stated,
since link speed is not internet throughput).

Benign `RuntimeError: ... attached to a different loop` tracebacks can
appear on stderr at exit (aiohttp session teardown); results are unaffected.
