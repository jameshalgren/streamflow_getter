# Research Plan: NWM vs. NextGen Statistical Comparison
**Repository:** https://github.com/jjohns314/streamflow_getter (fork of jameshalgren/streamflow_getter)  
**Institution:** Brigham Young University  
**Status:** Active planning. Reconciled with `docs/ROADMAP.md` (upstream, 2026-10-19).

---

## 1. Project Goal

Compare operational **National Water Model (NWM) v3.0 short-range streamflow forecasts** against **NextGen Research DataStream (NRDS)** output (which may include t-route routed flow) to evaluate whether differences between the two models are statistically significant. Initial focus: **Alabama (VPU 03W)**. Design must generalize to other VPUs with minimal code changes.

---

## 2. Next Steps

Work top to bottom. Steps within a phase can run in parallel. Phases 0–2 need no new package code; Phase 3 waits on the answers from Phase 1. Question IDs (Q1…) refer to §9.

### Phase 0 — Set up (no answers needed)

| # | Step | Done when |
|---|---|---|
| 1 | Push `docs/research-plan-roadmap` to the fork. Sign in as `jjohns314` when the Git Credential Manager window opens | Branch shows on github.com/jjohns314/streamflow_getter |
| 2 | Install [uv](https://docs.astral.sh/uv/) and the GitHub CLI (`gh`), then run `uv sync` and `uv run pytest` | Tests pass locally |
| 3 | Reset fork `main` to upstream. It carries one extra commit ("Add files via upload") that breaks "`main` tracks upstream" (§10). Do this only after step 1, so this plan is safe on its branch: `git switch main`, `git reset --hard upstream/main`, `git push --force-with-lease origin main` | Fork `main` matches upstream |

### Phase 1 — Get answers (ask early; everything in Phase 3 waits on these)

| # | Step | Done when |
|---|---|---|
| 4 | Send James this plan (branch link, or a PR to upstream if he wants it in the repo). Ask Q6 and Q7 | Scope and ownership agreed |
| 5 | Meet with advisor. Ask Q1, Q2, Q3 | NRDS package, lead times and study period chosen |

### Phase 2 — Look at the data by hand (start while waiting on Phase 1)

Use a notebook or scratch script outside `src/`; nothing here goes into the package yet.

| # | Step | Done when |
|---|---|---|
| 6 | Find NRDS t-route output for 03W around 2026-04-19. Open one file and record format, ID type (`nex-`, `wb-` or `cat-`), units, time zone and time step | Q4 and Q5 answered; §4.2 updated |
| 7 | Get the 03W crosswalk and check that it maps COMIDs to the ID type found in step 6 | Q8 answered |
| 8 | Pick 5–10 Alabama USGS gages with flow during the 2026-04-19 event; list gage ID, COMID and NextGen ID for each | Anchor list saved as a small CSV |
| 9 | For those COMIDs, pull one short-range cycle plus its `analysis_assim` `tm00` by hand and plot against NRDS | One side-by-side plot that looks plausible |

### Phase 3 — Code (after Phase 1)

| # | Step | Branch | Done when |
|---|---|---|---|
| 10 | The roadmap step James assigns (likely the Kerchunk vs native benchmark or RouteLink reach resolution) | `feature/<roadmap step>` | PR merged upstream |
| 11 | `nrds.py` + `crosswalk.py`, tested on the anchor gages | `feature/nrds-adapter` | PR open |
| 12 | `stats.py` + analysis for the 2026-04-19 event | `feature/stats-comparison` | First metrics table per gage and lead time |
| 13 | Extend to the full study period from Q3 | — | Results exported to Parquet / CSV |

---

## 3. Relationship to the Roadmap

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

## 4. Data Sources

### 4.1 National Water Model — Operational Short-Range

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

### 4.2 NextGen Research DataStream (NRDS) — T-route Output

NRDS packages t-route routed streamflow at NextGen **nexus points**. BYU has access through the CIROH partnership.

**Access points to investigate:**
- **CIROH Data Access Portal:** https://dataaccess.ciroh.org — browse for NextGen/NRDS datasets; check for Alabama / VPU 03W t-route output packages
- **Lynker Hydrofabric (S3):** `s3://lynker-spatial/hydrofabric/` — contains hydrofabric GeoPackages with the NWM↔NextGen crosswalk for 03W
- **CIROH JupyterHub:** https://ciroh.ua.edu — shared compute environment; pre-staged NRDS data may already be available there
- **HuggingFace:** https://huggingface.co/datasets/lynker-spatial/hydrofabric — alternative hydrofabric access

**Expected format:** CSV or Parquet files with columns similar to `time`, `nexus_id`, `streamflow_cms`. Confirm units and time zone on first data inspection.

**Key gotchas:**
- NRDS uses NextGen hydrofabric IDs, not NHDPlus COMIDs — a crosswalk is required before any comparison. This plan assumes nexus IDs (`nex-XXXXXXX`); the README lists `wb-*` / `cat-*`. Confirm which the output uses (Q5)
- The 03W crosswalk (NWM COMID → NextGen nexus) is **lossy**: multiple COMIDs average into one nexus, which biases flow low. Document and account for this in statistical interpretation. Sources: the Lynker hydrofabric, or the `nwmxwalk` repo named in `docs/nwm-notes.md`
- Confirm whether your NRDS package contains t-route output or raw catchment runoff — only routed flow is directly comparable to NWM `channel_rt`

---

## 5. Spatial Scope

### Initial: Alabama (VPU 03W)
- VPU 03W covers most of Alabama and is the **only VPU with a published NWM↔NextGen crosswalk** at this time
- Identify a set of Alabama USGS gages or representative nexus points as anchor locations
- Get their COMIDs through the roadmap's RouteLink reach resolution, then their NextGen nexus IDs from the crosswalk table

### Generalization path
- Parameterize all region-specific logic behind a `vpu` argument (e.g., `vpu="03W"`)
- Abstract crosswalk loading so other VPUs can be swapped in once their crosswalks become available
- Document which VPUs currently lack crosswalks in `docs/nwm-notes.md`

---

## 6. Code Plan

All new code follows the existing adapter pattern in `src/streamflow_getter/` — each source gets its own module with a `fetch(reach_ids, start, end, variable) -> pd.DataFrame` interface.

### 6.1 Modules

```
src/streamflow_getter/
├── nwm.py                # existing — retrospective only, keep as-is (gated)
├── <operational module>  # ROADMAP — operational fetch for all products; name agreed with James
├── nrds.py               # NEW — NRDS / t-route output reader
├── crosswalk.py          # NEW — NWM COMID ↔ NextGen nexus ID mapping
└── stats.py              # NEW — statistical comparison metrics
```

The operational fetcher is roadmap work (order of work, steps 1–3), not a separate short-range-only module. Contribute to it rather than writing a parallel `nwm_operational.py`.

### 6.2 Operational fetch — what this study needs from it

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

### 6.3 `nrds.py` — key functions

```python
def fetch_nrds(
    nexus_ids: list[str],
    start: str,
    end: str,
    source: str = "ciroh",   # "ciroh" | "local" | "s3"
) -> pd.DataFrame:
    """Load NRDS t-route output. Columns: time, nexus_id, streamflow (m3/s)."""
```

### 6.4 `crosswalk.py` — key functions

```python
def load_crosswalk(vpu: str = "03W") -> pd.DataFrame:
    """Return mapping of feature_id (COMID) → nexus_id for the given VPU."""

def align(nwm_df: pd.DataFrame, nrds_df: pd.DataFrame, vpu: str = "03W") -> pd.DataFrame:
    """Join NWM and NRDS on matched reach/nexus pairs and common valid times,
    keeping reference_time and lead_time from the NWM side."""
```

### 6.5 `stats.py` — metrics to implement

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

## 7. Analysis Workflow

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

## 8. Statistical Framework

For hydrological model comparison, standard metrics (NSE, KGE, PBIAS, RMSE) are expected by reviewers — not generic significance tests like t-tests. However, the following additional tests are appropriate:

- **Wilcoxon signed-rank test** — non-parametric test for whether median difference between NWM and NRDS is zero; appropriate because streamflow distributions are right-skewed
- **Mann-Whitney U** — if comparing distributions across sites rather than paired observations
- **Temporal autocorrelation check** — streamflow is autocorrelated; standard p-values from t-tests will be inflated. Use block bootstrap or note the limitation

**Null hypothesis:** NWM (t0 analysis, and each forecast lead time separately) and NRDS t-route streamflow are drawn from the same distribution at matched reach/nexus pairs.

---

## 9. Open Questions (resolve before coding)

"Answered by" says who to ask, or which step in §2 finds out by looking. Record each answer here, with the date, when you get it.

| ID | Question | Answered by | Blocks | Answer |
|---|---|---|---|---|
| Q1 | **Which NRDS package?** Which CIROH dataset holds Alabama t-route output, and where is it? | Advisor (step 5) | Steps 6, 11 | |
| Q2 | **Which lead times?** t0 (`analysis_assim` `tm00`) is the analysis-of-record. Which forecast lead times, if any, are also in scope? | Advisor (step 5) | Steps 12, 13 | |
| Q3 | **Study period?** Which dates beyond the 2026-04-19 event? Short range is 24 cycles × 18 lead times = 432 files per day (24 per day for one lead time); the roadmap's Kerchunk vs native benchmark gives the read cost | Advisor (step 5) | Step 13 | |
| Q4 | **NRDS units and time:** Is t-route output in m³/s? UTC? What time step? Is it routed flow, not raw catchment runoff? | Data (step 6) | Steps 9, 11 | |
| Q5 | **NRDS ID type:** Is output keyed by nexus (`nex-`) or by waterbody/catchment (`wb-`, `cat-`, as the README lists)? | Data (step 6) | Steps 7, 11 | |
| Q6 | **Upstream scope:** Do `nrds.py`, `crosswalk.py` and `stats.py` belong in `streamflow_getter`, or should the statistics live in a separate analysis repo or folder? The crosswalk is marked out of scope in `docs/nwm-notes.md` | James (step 4) | Steps 11, 12 | |
| Q7 | **Roadmap ownership:** Which roadmap step (benchmark, RouteLink, operational fetch) do you take, so the work isn't duplicated? | James (step 4) | Step 10 | |
| Q8 | **Crosswalk access:** Can you reach the 03W crosswalk (Lynker S3, CIROH JupyterHub or `nwmxwalk`), and does it map to the ID type from Q5? | Data (step 7) | Step 11 | |

---

## 10. Branch Strategy

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

## 11. References

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
