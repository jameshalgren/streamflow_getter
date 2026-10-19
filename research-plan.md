# Research Plan: NWM vs. NextGen Statistical Comparison
**Repository:** https://github.com/jjohns314/streamflow_getter (fork of jameshalgren/streamflow_getter)  
**Institution:** Brigham Young University  
**Status:** Active planning — not committed to repository

---

## 1. Project Goal

Compare operational **National Water Model (NWM) v3.0 short-range streamflow forecasts** against **NextGen Research DataStream (NRDS)** output (which may include t-route routed flow) to evaluate whether differences between the two models are statistically significant. Initial focus: **Alabama (VPU 03W)**. Design must generalize to other VPUs with minimal code changes.

---

## 2. Data Sources

### 2.1 National Water Model — Operational Short-Range

| Property | Value |
|---|---|
| Bucket | `gs://national-water-model` (GCS, public) |
| Alt bucket | `s3://noaa-nwm-pds` (AWS, available from 2025-01-01) |
| Path pattern | `nwm.YYYYMMDD/short_range/nwm.tCCz.short_range.channel_rt.fHHH.conus.nc` |
| Cycles | 00, 06, 12, 18 UTC (4 per day) |
| Forecast hours | f001 – f018 (18 hours per cycle) |
| Variable | `streamflow` (int32, scale_factor=0.01, units: m³/s) |
| Reach IDs | NHDPlusV2 COMIDs (`feature_id`) |
| File listing | `https://storage.googleapis.com/storage/v1/b/national-water-model/o?prefix=nwm.YYYYMMDD/short_range/` |

**Fetch strategy:** Plain HTTPS via the GCS JSON API — no Google Cloud SDK required. Download only files for the selected forecast hour (e.g., f001 for analysis-of-record, or a fixed lead time like f006). Filter to Alabama COMIDs immediately after reading each `.nc` to avoid holding full CONUS arrays in memory.

**Key gotchas:**
- Use the `valid_time` attribute inside the file, not the filename timestamp
- `streamflow` is encoded as int32; let xarray auto-decode via `scale_factor`
- `_FillValue = -99990` — mask before any statistics

### 2.2 NextGen Research DataStream (NRDS) — T-route Output

NRDS packages t-route routed streamflow at NextGen **nexus points**. BYU has access through the CIROH partnership.

**Access points to investigate:**
- **CIROH Data Access Portal:** https://dataaccess.ciroh.org — browse for NextGen/NRDS datasets; check for Alabama / VPU 03W t-route output packages
- **Lynker Hydrofabric (S3):** `s3://lynker-spatial/hydrofabric/` — contains hydrofabric GeoPackages with the NWM↔NextGen crosswalk for 03W
- **CIROH JupyterHub:** https://ciroh.ua.edu — shared compute environment; pre-staged NRDS data may already be available there
- **HuggingFace:** https://huggingface.co/datasets/lynker-spatial/hydrofabric — alternative hydrofabric access

**Expected format:** CSV or Parquet files with columns similar to `time`, `nexus_id`, `streamflow_cms`. Confirm units and time zone on first data inspection.

**Key gotchas:**
- NRDS uses NextGen hydrofabric IDs (`nex-XXXXXXX`), not NHDPlus COMIDs — a crosswalk is required before any comparison
- The 03W crosswalk (NWM COMID → NextGen nexus) is available in the Lynker hydrofabric but is **lossy**: multiple COMIDs average into one nexus, which biases flow low. Document and account for this in statistical interpretation.
- Confirm whether your NRDS package contains t-route output or raw catchment runoff — only routed flow is directly comparable to NWM `channel_rt`

---

## 3. Spatial Scope

### Initial: Alabama (VPU 03W)
- VPU 03W covers most of Alabama and is the **only VPU with a published NWM↔NextGen crosswalk** at this time
- Identify a set of Alabama USGS gages or representative nexus points as anchor locations
- Pull their COMIDs and corresponding NextGen nexus IDs from the crosswalk table

### Generalization path
- Parameterize all region-specific logic behind a `vpu` argument (e.g., `vpu="03W"`)
- Abstract crosswalk loading so other VPUs can be swapped in once their crosswalks become available
- Document which VPUs currently lack crosswalks in `docs/nwm-notes.md`

---

## 4. Code Plan

All new code follows the existing adapter pattern in `src/streamflow_getter/` — each source gets its own module with a `fetch(reach_ids, start, end, variable) -> pd.DataFrame` interface.

### 4.1 New modules

```
src/streamflow_getter/
├── nwm.py                # existing — retrospective only, keep as-is
├── nwm_operational.py    # NEW — short-range operational fetcher (GCS/S3)
├── nrds.py               # NEW — NRDS / t-route output reader
├── crosswalk.py          # NEW — NWM COMID ↔ NextGen nexus ID mapping
└── stats.py              # NEW — statistical comparison metrics
```

### 4.2 `nwm_operational.py` — key functions

```python
def list_files(date: str, cycle: str = "00", forecast_hour: int = 1) -> list[str]:
    """Return GCS HTTPS URLs for the given date/cycle/fHHH."""

def fetch_operational(
    reach_ids: list[int],
    start: str,
    end: str,
    cycle: str = "00",
    forecast_hour: int = 1,
) -> pd.DataFrame:
    """Download short-range channel_rt files and return long-format DataFrame.
    Columns: time (UTC), feature_id, streamflow (m3/s)."""
```

### 4.3 `nrds.py` — key functions

```python
def fetch_nrds(
    nexus_ids: list[str],
    start: str,
    end: str,
    source: str = "ciroh",   # "ciroh" | "local" | "s3"
) -> pd.DataFrame:
    """Load NRDS t-route output. Columns: time, nexus_id, streamflow (m3/s)."""
```

### 4.4 `crosswalk.py` — key functions

```python
def load_crosswalk(vpu: str = "03W") -> pd.DataFrame:
    """Return mapping of feature_id (COMID) → nexus_id for the given VPU."""

def align(nwm_df: pd.DataFrame, nrds_df: pd.DataFrame, vpu: str = "03W") -> pd.DataFrame:
    """Join NWM and NRDS on matched reach/nexus pairs and common timestamps."""
```

### 4.5 `stats.py` — metrics to implement

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
    """Run all metrics per reach/nexus pair. Returns summary DataFrame."""
```

---

## 5. Analysis Workflow

```
1. Select VPU and date range
        │
        ▼
2. Load crosswalk (crosswalk.load_crosswalk)
        │
        ▼
3. Fetch NWM operational short-range f001 (nwm_operational.fetch_operational)
   Fetch NRDS t-route output          (nrds.fetch_nrds)
        │
        ▼
4. Align on time + reach/nexus (crosswalk.align)
   — resample to common frequency if needed
   — flag and drop fill values
        │
        ▼
5. Compute statistics per reach pair (stats.compare)
        │
        ▼
6. Export results to CSV / Parquet
```

---

## 6. Statistical Framework

For hydrological model comparison, standard metrics (NSE, KGE, PBIAS, RMSE) are expected by reviewers — not generic significance tests like t-tests. However, the following additional tests are appropriate:

- **Wilcoxon signed-rank test** — non-parametric test for whether median difference between NWM and NRDS is zero; appropriate because streamflow distributions are right-skewed
- **Mann-Whitney U** — if comparing distributions across sites rather than paired observations
- **Temporal autocorrelation check** — streamflow is autocorrelated; standard p-values from t-tests will be inflated. Use block bootstrap or note the limitation

**Null hypothesis:** NWM short-range f001 and NRDS t-route streamflow are drawn from the same distribution at matched reach/nexus pairs.

---

## 7. Open Questions (resolve before coding)

- [ ] **Which NRDS package?** Confirm with advisor which specific CIROH dataset contains Alabama t-route output and its format/location
- [ ] **Which forecast hour?** f001 (analysis-of-record) is simplest; confirm with advisor if a longer lead time is intended
- [ ] **Date range?** Define the study period — drives how many files to download and storage requirements (~72 files/day × ~30 MB each = ~2 GB/day)
- [ ] **Crosswalk availability:** Verify the 03W crosswalk is accessible from Lynker S3 or CIROH JupyterHub
- [ ] **Unit confirmation for NRDS:** Verify NRDS t-route output is in m³/s before any comparison

---

## 8. Branch Strategy

Working in fork: `github.com/jjohns314/streamflow_getter`

| Branch | Purpose |
|---|---|
| `main` | Tracks upstream `jameshalgren/streamflow_getter` |
| `feature/nwm-operational` | `nwm_operational.py` + CLI integration |
| `feature/nrds-adapter` | `nrds.py` + crosswalk logic |
| `feature/stats-comparison` | `stats.py` + analysis scripts |

Open PRs to upstream (`jameshalgren`) once each module is tested and documented. Keep PRs focused — one module per PR.

---

## 9. References

- NWM operational data (GCS): https://console.cloud.google.com/storage/browser/national-water-model
- NWM operational data (AWS): `s3://noaa-nwm-pds`
- CIROH Data Access: https://dataaccess.ciroh.org
- Lynker Hydrofabric: `s3://lynker-spatial/hydrofabric/`
- Lynker Hydrofabric (HuggingFace): https://huggingface.co/datasets/lynker-spatial/hydrofabric
- Upstream repo: https://github.com/jameshalgren/streamflow_getter
- NWM technical notes: `docs/nwm-notes.md`
