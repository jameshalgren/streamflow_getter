"""CLI tests for explicit operational NWM date ranges."""

from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from streamflow_getter.cli import build_parser, main


def _range_arguments(tmp_path, *extra):
    return [
        "nwm-operational",
        "--start-date", "2026-04-19",
        "--end-date", "2026-04-21",
        "--cycle", "0",
        "--product", "short_range",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "1",
        "--no-t0",
        "--no-cache",
        *extra,
        "--out", str(tmp_path / "period.csv"),
    ]


def _combined_frame(configs):
    rows = []

    for config in configs:
        rows.append({
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "requested_product": config.product,
            "product": config.product,
            "domain": config.domain,
            "lead_hour": 1,
            "feature_id": 3586192,
            "valid_time": (
                f"{config.date}T01:00:00"
            ),
            "reference_time": (
                f"{config.date}T00:00:00"
            ),
            "streamflow_m3s": 0.41,
            "method": "kerchunk",
        })

    return pd.DataFrame(rows)


def test_parser_accepts_explicit_date_range(tmp_path):
    args = build_parser().parse_args(
        _range_arguments(tmp_path)
    )

    assert args.date is None
    assert args.start_date == "2026-04-19"
    assert args.end_date == "2026-04-21"


def test_parser_rejects_date_and_start_date_together(tmp_path):
    with pytest.raises(SystemExit) as caught:
        build_parser().parse_args([
            "nwm-operational",
            "--date", "2026-04-19",
            "--start-date", "2026-04-19",
            "--end-date", "2026-04-21",
            "--reach", "3586192",
            "--out", str(tmp_path / "flows.csv"),
        ])

    assert caught.value.code == 2


def test_range_requires_end_date_before_retrieval(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_requests

    fetch = Mock(
        side_effect=AssertionError(
            "Range retrieval must not start"
        )
    )

    monkeypatch.setattr(
        operational_requests,
        "fetch_operational_configs",
        fetch,
    )

    with pytest.raises(
        ValueError,
        match="--end-date is required",
    ):
        main([
            "nwm-operational",
            "--start-date", "2026-04-19",
            "--reach", "3586192",
            "--out", str(tmp_path / "flows.csv"),
        ])

    fetch.assert_not_called()


def test_single_date_rejects_unpaired_end_date(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_nwm

    fetch = Mock(
        side_effect=AssertionError(
            "Single-date retrieval must not start"
        )
    )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fetch,
    )

    with pytest.raises(
        ValueError,
        match="cannot be used with --date",
    ):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--end-date", "2026-04-21",
            "--reach", "3586192",
            "--out", str(tmp_path / "flows.csv"),
        ])

    fetch.assert_not_called()


def test_invalid_range_stops_before_retrieval(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_requests

    fetch = Mock(
        side_effect=AssertionError(
            "Invalid range reached retrieval"
        )
    )

    monkeypatch.setattr(
        operational_requests,
        "fetch_operational_configs",
        fetch,
    )

    with pytest.raises(
        ValueError,
        match="must not precede",
    ):
        main([
            "nwm-operational",
            "--start-date", "2026-04-21",
            "--end-date", "2026-04-19",
            "--reach", "3586192",
            "--out", str(tmp_path / "flows.csv"),
        ])

    fetch.assert_not_called()


def test_range_uses_planner_executor_and_preserves_export_schema(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_nwm
    from streamflow_getter import operational_requests
    from streamflow_getter import output

    captured = {}

    single_fetch = Mock(
        side_effect=AssertionError(
            "Range request used single-date retrieval"
        )
    )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        single_fetch,
    )

    def fake_range_fetch(
        configs,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0=True,
        cache_dir=None,
    ):
        configs = list(configs)

        captured["configs"] = configs
        captured["reach_ids"] = list(reach_ids)
        captured["start_hour"] = start_hour
        captured["end_hour"] = end_hour
        captured["include_t0"] = include_t0
        captured["cache_dir"] = cache_dir

        return _combined_frame(configs)

    monkeypatch.setattr(
        operational_requests,
        "fetch_operational_configs",
        fake_range_fetch,
    )

    def fake_write(
        frame,
        destination,
        *,
        output_format=None,
    ):
        captured["written"] = frame.copy()
        captured["destination"] = Path(destination)
        captured["output_format"] = output_format
        return Path(destination)

    monkeypatch.setattr(
        output,
        "write_timeseries",
        fake_write,
    )

    assert main(
        _range_arguments(tmp_path)
    ) == 0

    assert [
        (
            config.date,
            config.cycle,
            config.product,
        )
        for config in captured["configs"]
    ] == [
        ("2026-04-19", 0, "short_range"),
        ("2026-04-20", 0, "short_range"),
        ("2026-04-21", 0, "short_range"),
    ]

    assert captured["reach_ids"] == [3586192]
    assert captured["start_hour"] == 1
    assert captured["end_hour"] == 1
    assert captured["include_t0"] is False
    assert captured["cache_dir"] is None

    written = captured["written"]

    assert len(written) == 3
    assert "requested_product" not in written.columns
    assert list(written["forecast_date"]) == [
        "2026-04-19",
        "2026-04-20",
        "2026-04-21",
    ]

    single_fetch.assert_not_called()


def test_single_date_keeps_existing_retrieval_path(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_nwm
    from streamflow_getter import operational_requests
    from streamflow_getter import output

    captured = {}

    def fake_single(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0=True,
        cache_dir=None,
    ):
        captured["config"] = config
        captured["cache_dir"] = cache_dir

        return pd.DataFrame([{
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": config.product,
            "domain": config.domain,
            "lead_hour": 1,
            "feature_id": reach_ids[0],
            "valid_time": "2026-04-19T01:00:00",
            "reference_time": "2026-04-19T00:00:00",
            "streamflow_m3s": 0.41,
            "method": "kerchunk",
        }])

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fake_single,
    )

    range_fetch = Mock(
        side_effect=AssertionError(
            "Single-date request used range executor"
        )
    )

    monkeypatch.setattr(
        operational_requests,
        "fetch_operational_configs",
        range_fetch,
    )

    monkeypatch.setattr(
        output,
        "write_timeseries",
        lambda frame, destination, output_format=None:
            Path(destination),
    )

    assert main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "1",
        "--no-t0",
        "--no-cache",
        "--out", str(tmp_path / "single.csv"),
    ]) == 0

    assert captured["config"].date == "2026-04-19"
    assert captured["cache_dir"] is None

    range_fetch.assert_not_called()

def _recent_arguments(tmp_path, days="3"):
    return [
        "nwm-operational",
        "--recent-days", days,
        "--cycle", "0",
        "--product", "short_range",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "1",
        "--no-t0",
        "--no-cache",
        "--out", str(tmp_path / "recent.csv"),
    ]


def test_parser_accepts_recent_days(tmp_path):
    args = build_parser().parse_args(
        _recent_arguments(tmp_path)
    )

    assert args.date is None
    assert args.start_date is None
    assert args.recent_days == 3
    assert args.end_date is None


def test_recent_days_uses_resolved_absolute_period(
    monkeypatch,
    tmp_path,
    capsys,
):
    from streamflow_getter import operational_requests
    from streamflow_getter import output
    from streamflow_getter import request_planning

    recent = Mock(
        return_value=(
            "2026-04-19",
            "2026-04-21",
        )
    )

    monkeypatch.setattr(
        request_planning,
        "resolve_recent_date_range",
        recent,
    )

    captured = {}

    def fake_fetch(
        configs,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0=True,
        cache_dir=None,
    ):
        configs = list(configs)

        captured["configs"] = configs
        captured["cache_dir"] = cache_dir

        return _combined_frame(configs)

    monkeypatch.setattr(
        operational_requests,
        "fetch_operational_configs",
        fake_fetch,
    )

    monkeypatch.setattr(
        output,
        "write_timeseries",
        lambda frame, destination, output_format=None:
            Path(destination),
    )

    assert main(
        _recent_arguments(tmp_path)
    ) == 0

    recent.assert_called_once_with(3)

    assert [
        config.date
        for config in captured["configs"]
    ] == [
        "2026-04-19",
        "2026-04-20",
        "2026-04-21",
    ]

    assert captured["cache_dir"] is None

    output = capsys.readouterr().out

    assert (
        "Resolved --recent-days 3 to UTC dates "
        "2026-04-19 through 2026-04-21"
        in output
    )


def test_recent_days_rejects_invalid_count_before_retrieval(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_requests

    fetch = Mock(
        side_effect=AssertionError(
            "Invalid recent window reached retrieval"
        )
    )

    monkeypatch.setattr(
        operational_requests,
        "fetch_operational_configs",
        fetch,
    )

    with pytest.raises(
        ValueError,
        match="positive integer",
    ):
        main(
            _recent_arguments(
                tmp_path,
                days="0",
            )
        )

    fetch.assert_not_called()


def test_recent_days_rejects_end_date(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_requests

    fetch = Mock(
        side_effect=AssertionError(
            "Invalid recent/end-date request reached retrieval"
        )
    )

    monkeypatch.setattr(
        operational_requests,
        "fetch_operational_configs",
        fetch,
    )

    with pytest.raises(
        ValueError,
        match="requires --start-date",
    ):
        main(
            _recent_arguments(tmp_path)
            + [
                "--end-date",
                "2026-04-21",
            ]
        )

    fetch.assert_not_called()
