# streamflow_getter

Download streamflow time series for specific river reaches from public
hydrologic model output, using one command-line tool. A single-page map
website will sit on top of the same tool, so anything the website does, the
CLI can do.

> **Status:** early development. Nothing below works yet except where marked.

## Goal

Pick a reach, pick a date range, get a time series file.

| Source | Reach ID | Status |
|---|---|---|
| NOAA National Water Model (NWM) | `feature_id` (COMID) | first target |
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
```

The command name and flags will change as the first adapter takes shape.

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

We are two developers working on `main` while the structure settles. Open an
issue or ping the other developer before large changes.
