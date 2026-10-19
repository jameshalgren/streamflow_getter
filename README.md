# streamflow_getter

Download streamflow time series for specific river reaches from public
hydrologic model output, using one command-line tool. A single-page map
website will sit on top of the same tool, so anything the website does, the
CLI can do.

> **Status:** early development. The `nwm` command works (CONUS retrospective v3.0 and v2.1, by reach or USGS gage).

## Goal

Pick a reach, pick a date range, get a time series file.

| Source | Reach ID | Status |
|---|---|---|
| NOAA National Water Model (NWM) | `feature_id` (COMID) | working (v3.0 retrospective) |
| NextGen Research DataStream (NRDS) | NextGen hydrofabric IDs (`wb-*`, `cat-*`) | planned |
| GEOGLOWS | `LINKNO` | planned |

Each source uses a different hydrofabric, so each gets its own adapter that
turns a reach ID into that source's native lookup. Crosswalks between
hydrofabrics come later.

## Planned usage

```bash
# NWM streamflow for two reaches, as CSV
streamflow-getter nwm --reach 101 --reach 179 \
    --start 2020-01-01 --end 2020-01-31 --out flow.csv

# ...or by USGS gage ID, from the older v2.1 retrospective
streamflow-getter nwm --gage 01646500 --version 2.1 \
    --start 2015-05-23 --end 2015-06-24 --out flow.csv
```

Flags may change. Output columns: `time` (UTC), `feature_id`, `streamflow` (m³/s).
Background on the NWM network and data: [docs/nwm-notes.md](docs/nwm-notes.md).

## Design

- **CLI first.** Core logic lives in a Python library; the CLI is a thin
  wrapper. The website will call the same library through the CLI.
- **One adapter per source**, behind a common interface:
  `fetch(reach_ids, start, end, variable) -> time series`.
- **Output:** CSV to start, Parquet later.

## Development

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <this repo>
cd streamflow_getter
uv sync
uv run streamflow-getter --help
uv run pytest
```

Run every Python command through `uv run`.

## Layout

```
src/streamflow_getter/   library and CLI
tests/                   tests
```

## Contributing

`main` is protected: no direct pushes. All changes arrive by pull request and
need one approval and a passing `test` check. PRs are squash-merged.

**Maintainer:** work on a branch in this repo.

```bash
git switch -c my-change
# ...edit, commit...
git push -u origin my-change
gh pr create --fill
```

**Contributors:** work from your own fork.

```bash
gh repo fork jameshalgren/streamflow_getter --clone
cd streamflow_getter
git remote -v                      # origin = your fork, upstream = this repo
git switch -c my-change
# ...edit, commit...
git push -u origin my-change
gh pr create --repo jameshalgren/streamflow_getter --fill
```

Keep your fork current before starting new work:

```bash
gh repo sync <your-username>/streamflow_getter
git switch main && git pull
```

Keep branches short-lived and PRs small.
