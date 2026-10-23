# Research Plan: NWM vs. NextGen Statistical Comparison
**Repository:** https://github.com/jjohns314/streamflow_getter (fork of jameshalgren/streamflow_getter)  
**Institution:** Brigham Young University  
**Status:** Active planning. Reconciled with `docs/ROADMAP.md` (upstream, 2026-10-19).

---

## 1. Project Goal

Compare operational **National Water Model (NWM) v3.0 short-range streamflow forecasts** against **NextGen Research DataStream (NRDS)** output (which may include t-route routed flow) to evaluate whether differences between the two models are statistically significant. Initial focus: **Alabama (VPU 03W)**. Design must generalize to other VPUs with minimal code changes.

---

## 2. Relationship to the Roadmap

`docs/ROADMAP.md` is the upstream plan for the data tool itself; this document is a study that uses it. Where they overlap, the roadmap wins and this plan builds on it rather than duplicating it.

| Area | Roadmap (upstream) | This plan |
|---|---|---|
| Operational NWM fetch | Owns it: all products, Kerchunk first, native fallback, local reference cache | Uses it; contributes the short-range pieces it needs |
| Reach resolution | RouteLink / channel hydrofabric (gage, point, bbox, polygon) | Uses it to pick Alabama gages and their COMIDs |
| Forecast t0 | `analysis_assim` `tm00` added by default (`--no-t0` to turn off) | Uses t0 as the analysis-of-record series |
| Output format | Parquet + CSV, with forecast reference time and lead time columns | Same columns throughout |
| Default test case | Forecast of 2026-04-19 (Alabama event) | First study date |
| NRDS, crosswalk, statistics | Not covered (`docs/nwm-notes.md` lists the crosswalk as out of scope for now) | New; scope agreed with James before any upstream PR |
| Retrospective, GEOGLOWS | Gated (Josh Cunningham, Riley Hales) | Not used; `nwm.py` stays as-is |

---

## 3. Data Sources

### 3.1 National Water Model — Operational Short-Range

| Property | Value |
|---|---|
| Bucket | `gs://national-water-model` (GCS, public, from 2018-09-17) |
| Alt bucket | `s3://noaa-nwm-pds` (AWS; "from 2025-01-01" per notes, to verify, see roadmap TODO) |
| Kerchunk references | `s3://ciroh-nwm-zarr-copy/national-water-model/nwm.YYYYMMDD/<product>/<file>.nc.json` |
| Path pattern | `nwm.YYYYMMDD/short_range/nwm.tCCz.short_range.channel_rt.fHHH.conus.nc` |
| Cycles | Hourly, 00 – 23 UTC (24 per day) |
| Forecast hours | f001 – f018 (18 hours per cycle) |
| t0 (analysis) | `nwm.YYYYMMDD/analysis_assim/nwm.tCCz.analysis_assim.channel_rt.tm00.conus.nc` |
| Variable | `streamflow` (int32, scale_factor=0.01, units: m³/s) |
| Reach IDs | NHDPlusV2 COMIDs (`feature_id`) |

**Fetch strategy:** Follow the roadmap: read through the CIROH Kerchunk references first and fall back to native NetCDF files (URLs from `nwmurl`), caching references locally. Select reaches by Alabama COMIDs as early as possible so full CONUS arrays are never held in memory. The roadmap's benchmark (Kerchunk vs native on 2026-04-19) decides the default path.

**Analysis-of-record:** Use `analysis_assim` `tm00` (lead time 0), which the roadmap fetches by default with each forecast. f001 is a one-hour forecast, not an analysis.

**Key gotchas:**
- Use the `valid_time` attribute inside the file, not the filename timestamp
- `streamflow` is encoded as int32; let xarray auto-decode via `scale_factor`
- `_FillValue = -99990` — mask before any statistics
- `channel_rt` files have no lat/lon or gage IDs; resolve reaches through RouteLink

### 3.2 NextGen Research DataStream (NRDS) — T-route Output

NRDS packages t-route routed streamflow at NextGen **nexus points**. BYU has access through the CIROH partnership.

**Access points to investigate:**
- **CIROH Data Access Portal:** https://dataaccess.ciroh.org — browse for NextGen/NRDS datasets; check for Alabama / VPU 03W t-route output packages
- **Lynker Hydrofabric (S3):** `s3://lynker-spatial/hydrofabric/` — contains hydrofabric GeoPackages with the NWM↔NextGen crosswalk for 03W
- **CIROH JupyterHub:** https://ciroh.ua.edu — shared compute environment; pre-staged NRDS data may already be available there
- **HuggingFace:** https://huggingface.co/datasets/lynker-spatial/hydrofabric — alternative hydrofabric access

**Expected format:** CSV or Parquet files with columns similar to `time`, `nexus_id`, `streamflow_cms`. Confirm units and time zone on first data inspection.

**Key gotchas:**
- NRDS uses NextGen hydrofabric IDs (`nex-XXXXXXX`), not NHDPlus COMIDs — a crosswalk is required before any comparison
- The 03W crosswalk (NWM COMID → NextGen nexus) is **lossy**: multiple COMIDs average into one nexus, which biases flow low. Document and account for this in statistical interpretation. Sources: the Lynker hydrofabric, or the `nwmxwalk` repo named in `docs/nwm-notes.md`
- Confirm whether your NRDS package contains t-route output or raw catchment runoff — only routed flow is directly comparable to NWM `channel_rt`

---

## 4. Spatial Scope

### Initial: Alabama (VPU 03W)
- VPU 03W covers most of Alabama and is the **only VPU with a published NWM↔NextGen crosswalk** at this time
- Identify a set of Alabama USGS gages or representative nexus points as anchor locations
- Get their COMIDs through the roadmap's RouteLink reach resolution, then their NextGen nexus IDs from the crosswalk table

### Generalization path
- Parameterize all region-specific logic behind a `vpu` argument (e.g., `vpu="03W"`)
- Abstract crosswalk loading so other VPUs can be swapped in once their crosswalks become available
- Document which VPUs currently lack crosswalks in `docs/nwm-notes.md`

---

## 5. Code Plan

All new code follows the existing adapter pattern in `src/streamflow_getter/` — each source gets its own module with a `fetch(reach_ids, start, end, variable) -> pd.DataFrame` interface.

### 5.1 Modules

```
src/streamflow_getter/
├── nwm.py                # existing — retrospective only, keep as-is (gated)
├── <operational module>  # ROADMAP — operational fetch for all products; name agreed with James
├── nrds.py               # NEW — NRDS / t-route output reader
├── crosswalk.py          # NEW — NWM COMID ↔ NextGen nexus ID mapping
└── stats.py              # NEW — statistical comparison metrics
```

The operational fetcher is roadmap work (order of work, steps 1–3), not a separate short-range-only module. Contribute to it rather than writing a parallel `nwm_operational.py`.

### 5.2 Operational fetch — what this study needs from it

```python
def fetch_operational(
    reach_ids: list[int],
    start: str,
    end: str,
    product: str = "short_range",
    cycles: list[int] | None = None,     # None = every cycle in range
    lead_times: list[int] | None = None, # None = all; [0] = t0 only
    t0: bool = True,                     # add analysis_assim tm00 (roadmap default)
) -> pd.DataFrame:
    """Columns: reference_time, lead_time, time (valid, UTC), feature_id,
    streamflow (m3/s), source_product."""
```

Keeping `reference_time` and `lead_time` matters here: each valid time appears in up to 18 forecasts plus the analysis, so `time` alone does not identify a row.

### 5.3 `nrds.py` — key functions

```python
def fetch_nrds(
    nexus_ids: list[str],
    start: str,
    end: str,
    source: str = "ciroh",   # "ciroh" | "local" | "s3"
) -> pd.DataFrame:
    """Load NRDS t-route output. Columns: time, nexus_id, streamflow (m3/s)."""
```

### 5.4 `crosswalk.py` — key functions

```python
def load_crosswalk(vpu: str = "03W") -> pd.DataFrame:
    """Return mapping of feature_id (COMID) → nexus_id for the given VPU."""

def align(nwm_df: pd.DataFrame, nrds_df: pd.DataFrame, vpu: str = "03W") -> pd.DataFrame:
    """Join NWM and NRDS on matched reach/nexus pairs and common valid times,
    keeping reference_time and lead_time from the NWM side."""
```

### 5.5 `stats.py` — metrics to implement

```python
def nse(observed, simulated) -> float:
    """Nash-Sutcliffe Efficiency. Range: -inf to 1.0 (1.0 = perfect)."""

def kge(observed, simulated) -> float:
    """Kling-Gupta Efficiency. Range: -inf to 1.0."""

def pbias(observed, simulated) -> float:
    """Percent bias. 0% = no bias."""

def rmse(observed, simulated) -> float:
    """Root Mean Square Error (m3/s)."""

def compare(aligned_df: pd.DataFrame) -> pd.DataFrame:
    """Run all metrics per reach/nexus pair and lead time. Returns summary DataFrame."""
```

---

## 6. Analysis Workflow

```
1. Select VPU and date range (start with the 2026-04-19 Alabama event)
        │
        ▼
2. Resolve gages → COMIDs (roadmap RouteLink), load crosswalk (crosswalk.load_crosswalk)
        │
        ▼
3. Fetch NWM operational short-range + t0 (roadmap operational fetch)
   Fetch NRDS t-route output              (nrds.fetch_nrds)
        │
        ▼
4. Align on valid time + reach/nexus (crosswalk.align)
   — resample to common frequency if needed
   — flag and drop fill values
        │
        ▼
5. Compute statistics per reach pair and lead time (stats.compare)
        │
        ▼
6. Export results to Parquet / CSV (roadmap output format)
```

---

## 7. Statistical Framework

For hydrological model comparison, standard metrics (NSE, KGE, PBIAS, RMSE) are expected by reviewers — not generic significance tests like t-tests. However, the following additional tests are appropriate:

- **Wilcoxon signed-rank test** — non-parametric test for whether median difference between NWM and NRDS is zero; appropriate because streamflow distributions are right-skewed
- **Mann-Whitney U** — if comparing distributions across sites rather than paired observations
- **Temporal autocorrelation check** — streamflow is autocorrelated; standard p-values from t-tests will be inflated. Use block bootstrap or note the limitation

**Null hypothesis:** NWM (t0 analysis, and each forecast lead time separately) and NRDS t-route streamflow are drawn from the same distribution at matched reach/nexus pairs.

---

## 8. Open Questions (resolve before coding)

- [ ] **Which NRDS package?** Confirm with advisor which specific CIROH dataset contains Alabama t-route output and its format/location
- [ ] **Which lead times?** t0 (`analysis_assim` `tm00`) is the analysis-of-record; confirm with advisor which forecast lead times (if any) are also intended
- [ ] **Date range?** Define the study period beyond the 2026-04-19 event. Short range is 24 cycles × 18 lead times = 432 files per day (24 per day for a single lead time); get read cost from the roadmap's Kerchunk vs native benchmark
- [ ] **Crosswalk availability:** Verify the 03W crosswalk is accessible from Lynker S3, CIROH JupyterHub, or `nwmxwalk`
- [ ] **Unit confirmation for NRDS:** Verify NRDS t-route output is in m³/s before any comparison
- [ ] **Upstream scope (James):** Do `nrds.py`, `crosswalk.py` and `stats.py` belong in `streamflow_getter`, or should the statistics live in a separate analysis repo or folder? The crosswalk is currently marked out of scope in `docs/nwm-notes.md`
- [ ] **Operational fetch ownership (James):** Who builds which roadmap step (benchmark, RouteLink, operational fetch), so the work is not duplicated

---

## 9. Branch Strategy

Working in fork: `github.com/jjohns314/streamflow_getter`

| Branch | Purpose |
|---|---|
| `main` | Tracks upstream `jameshalgren/streamflow_getter`; no direct commits |
| `docs/research-plan-roadmap` | This plan, reconciled with the roadmap |
| `feature/<roadmap step>` | Roadmap operational-fetch work agreed with James (e.g. RouteLink reach resolution) |
| `feature/nrds-adapter` | `nrds.py` + crosswalk logic |
| `feature/stats-comparison` | `stats.py` + analysis scripts |

Open PRs to upstream (`jameshalgren`) once each module is tested and documented. Keep PRs focused — one module per PR. Sync `main` from upstream before starting each branch.

---

## 10. References

- Upstream roadmap: `docs/ROADMAP.md`
- NWM technical notes: `docs/nwm-notes.md`
- NWM operational data (GCS): https://console.cloud.google.com/storage/browser/national-water-model
- NWM operational data (AWS): `s3://noaa-nwm-pds`
- CIROH Kerchunk references: `s3://ciroh-nwm-zarr-copy/national-water-model/`
- CIROH Data Access: https://dataaccess.ciroh.org
- CIROH Data Access docs: https://hub.ciroh.org/docs/products/data-management/dataaccess/
- Lynker Hydrofabric: `s3://lynker-spatial/hydrofabric/`
- Lynker Hydrofabric (HuggingFace): https://huggingface.co/datasets/lynker-spatial/hydrofabric
- Upstream repo: https://github.com/jameshalgren/streamflow_getter
