"""CLI policy tests for operational NWM reference caching."""

from pathlib import Path

import pandas as pd
import pytest

from streamflow_getter.cli import build_parser, main


DEFAULT_CACHE_DIR = "~/.cache/streamflow_getter"


def _arguments(tmp_path, *cache_args):
    return [
        "nwm-operational",
        "--date", "2026-04-19",
        "--cycle", "0",
        "--product", "short_range",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "1",
        "--no-t0",
        *cache_args,
        "--out", str(tmp_path / "flows.csv"),
    ]


def _run_and_capture_cache(monkeypatch, tmp_path, *cache_args):
    from streamflow_getter import operational_nwm, output

    captured = {}

    def fake_fetch(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0=True,
        cache_dir=None,
    ):
        captured["config"] = config
        captured["reach_ids"] = list(reach_ids)
        captured["start_hour"] = start_hour
        captured["end_hour"] = end_hour
        captured["include_t0"] = include_t0
        captured["cache_dir"] = cache_dir

        return pd.DataFrame([{
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": config.product,
            "domain": config.domain,
            "lead_hour": start_hour,
            "feature_id": reach_ids[0],
            "valid_time": "2026-04-19T01:00:00",
            "reference_time": "2026-04-19T00:00:00",
            "streamflow_m3s": 0.41,
            "method": "kerchunk",
        }])

    def fake_write(frame, destination, *, output_format=None):
        captured["output_rows"] = len(frame)
        captured["output_format"] = output_format
        return Path(destination)

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fake_fetch,
    )
    monkeypatch.setattr(
        output,
        "write_timeseries",
        fake_write,
    )

    assert main(_arguments(tmp_path, *cache_args)) == 0
    return captured


def test_operational_parser_defaults_to_persistent_reference_cache(tmp_path):
    args = build_parser().parse_args(_arguments(tmp_path))

    assert args.cache_dir == DEFAULT_CACHE_DIR


def test_operational_cli_passes_default_reference_cache(monkeypatch, tmp_path):
    captured = _run_and_capture_cache(monkeypatch, tmp_path)

    assert captured["cache_dir"] == DEFAULT_CACHE_DIR
    assert captured["reach_ids"] == [3586192]
    assert captured["include_t0"] is False


def test_operational_cli_accepts_cache_directory_override(monkeypatch, tmp_path):
    override = tmp_path / "references"

    captured = _run_and_capture_cache(
        monkeypatch,
        tmp_path,
        "--cache-dir",
        str(override),
    )

    assert captured["cache_dir"] == str(override)


def test_operational_cli_no_cache_passes_none(monkeypatch, tmp_path):
    captured = _run_and_capture_cache(
        monkeypatch,
        tmp_path,
        "--no-cache",
    )

    assert captured["cache_dir"] is None


def test_operational_cli_rejects_cache_override_with_no_cache(tmp_path):
    with pytest.raises(SystemExit) as caught:
        build_parser().parse_args(
            _arguments(
                tmp_path,
                "--cache-dir",
                str(tmp_path / "references"),
                "--no-cache",
            )
        )

    assert caught.value.code == 2
