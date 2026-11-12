"""CLI tests for operational run-manifest publication."""

import json
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from streamflow_getter.cli import main


SERIES_COLUMNS = [
    "forecast_date",
    "forecast_cycle",
    "product",
    "domain",
    "lead_hour",
    "feature_id",
    "valid_time",
    "reference_time",
    "streamflow_m3s",
    "method",
]


COMBINED_COLUMNS = [
    "forecast_date",
    "forecast_cycle",
    "requested_product",
    "product",
    "domain",
    "lead_hour",
    "feature_id",
    "valid_time",
    "reference_time",
    "streamflow_m3s",
    "method",
]


def _single_frame():
    return pd.DataFrame(
        [
            {
                "forecast_date": "2026-04-19",
                "forecast_cycle": 0,
                "product": "short_range",
                "domain": "conus",
                "lead_hour": 1,
                "feature_id": 3586192,
                "valid_time": "2026-04-19T01:00:00",
                "reference_time": "2026-04-19T00:00:00",
                "streamflow_m3s": 0.41,
                "method": "kerchunk",
            },
        ],
        columns=SERIES_COLUMNS,
    )


def _period_frame(configs):
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

    return pd.DataFrame(
        rows,
        columns=COMBINED_COLUMNS,
    )


def _load_manifest(data_path):
    manifest_path = Path(
        str(data_path) + ".manifest.json"
    )

    assert manifest_path.exists()

    with manifest_path.open(
        encoding="utf-8"
    ) as file:
        return manifest_path, json.load(file)


def test_single_date_cli_publishes_manifest_without_schema_drift(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_nwm

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        Mock(
            return_value=_single_frame()
        ),
    )

    output = tmp_path / "single.csv"

    assert main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--cycle", "0",
        "--product", "short_range",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "1",
        "--no-t0",
        "--no-cache",
        "--out", str(output),
    ]) == 0

    exported = pd.read_csv(
        output
    )

    assert list(
        exported.columns
    ) == SERIES_COLUMNS

    assert (
        "requested_product"
        not in exported.columns
    )

    manifest_path, manifest = (
        _load_manifest(output)
    )

    assert manifest_path.name == (
        "single.csv.manifest.json"
    )

    assert manifest["status"] == "complete"

    assert manifest["selection"]["temporal"] == {
        "mode": "single_date",
        "requested_date": "2026-04-19",
        "resolved_start_date": "2026-04-19",
        "resolved_end_date": "2026-04-19",
    }

    assert manifest["cache_policy"] == {
        "mode": "disabled",
    }

    assert manifest["request"]["configs"] == [
        {
            "forecast_date": "2026-04-19",
            "forecast_cycle": 0,
            "requested_product": "short_range",
            "domain": "conus",
            "nwm_version": "3.0",
        }
    ]

    assert manifest["result"]["row_count"] == 1

    assert manifest["completeness"]["complete"] is True


def test_explicit_period_cli_manifest_retains_resolved_request(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_requests

    def fake_fetch(
        configs,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0=True,
        cache_dir=None,
    ):
        return _period_frame(
            list(configs)
        )

    monkeypatch.setattr(
        operational_requests,
        "fetch_operational_configs",
        fake_fetch,
    )

    output = tmp_path / "period.csv"

    assert main([
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
        "--out", str(output),
    ]) == 0

    exported = pd.read_csv(
        output
    )

    assert len(exported) == 3

    assert (
        "requested_product"
        not in exported.columns
    )

    _, manifest = _load_manifest(
        output
    )

    assert manifest["selection"]["temporal"] == {
        "mode": "explicit_period",
        "requested_start_date": "2026-04-19",
        "requested_end_date": "2026-04-21",
        "resolved_start_date": "2026-04-19",
        "resolved_end_date": "2026-04-21",
    }

    assert [
        config["forecast_date"]
        for config in manifest["request"]["configs"]
    ] == [
        "2026-04-19",
        "2026-04-20",
        "2026-04-21",
    ]

    assert manifest["completeness"] == {
        "mode": "strict",
        "expected_row_count": 3,
        "actual_row_count": 3,
        "missing_row_count": 0,
        "extra_row_count": 0,
        "complete": True,
    }


def test_recent_days_manifest_records_relative_and_resolved_window(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_requests
    from streamflow_getter import request_planning

    monkeypatch.setattr(
        request_planning,
        "resolve_recent_date_range",
        Mock(
            return_value=(
                "2026-04-19",
                "2026-04-21",
            )
        ),
    )

    monkeypatch.setattr(
        operational_requests,
        "fetch_operational_configs",
        lambda configs, reach_ids, start_hour, end_hour,
        include_t0=True, cache_dir=None:
            _period_frame(list(configs)),
    )

    output = tmp_path / "recent.csv"

    assert main([
        "nwm-operational",
        "--recent-days", "3",
        "--cycle", "0",
        "--product", "short_range",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "1",
        "--no-t0",
        "--no-cache",
        "--out", str(output),
    ]) == 0

    _, manifest = _load_manifest(
        output
    )

    assert manifest["selection"]["temporal"] == {
        "mode": "recent_days",
        "requested_days": 3,
        "resolved_start_date": "2026-04-19",
        "resolved_end_date": "2026-04-21",
    }


def test_persistent_cache_policy_is_recorded(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_nwm

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        Mock(
            return_value=_single_frame()
        ),
    )

    output = tmp_path / "cached.csv"

    assert main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "1",
        "--no-t0",
        "--cache-dir", "/tmp/example-nwm-cache",
        "--out", str(output),
    ]) == 0

    _, manifest = _load_manifest(
        output
    )

    assert manifest["cache_policy"] == {
        "mode": "persistent",
        "directory": "/tmp/example-nwm-cache",
    }


def test_existing_manifest_stops_before_retrieval(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_nwm

    fetch = Mock(
        side_effect=AssertionError(
            "retrieval started despite existing manifest"
        )
    )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fetch,
    )

    output = tmp_path / "existing.csv"

    manifest_path = Path(
        str(output) + ".manifest.json"
    )

    manifest_path.write_text(
        "preserve-me",
        encoding="utf-8",
    )

    with pytest.raises(
        FileExistsError,
        match="Manifest already exists",
    ):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--reach", "3586192",
            "--start-hour", "1",
            "--end-hour", "1",
            "--no-t0",
            "--out", str(output),
        ])

    fetch.assert_not_called()

    assert not output.exists()

    assert manifest_path.read_text(
        encoding="utf-8"
    ) == "preserve-me"


def test_single_date_manifest_uses_literal_analysis_source_metadata(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_nwm

    frame = pd.DataFrame(
        [
            {
                "forecast_date": "2026-04-19",
                "forecast_cycle": 0,
                "product": "analysis_assim",
                "domain": "conus",
                "lead_hour": 0,
                "feature_id": 3586192,
                "valid_time": "2026-04-19T00:00:00",
                "reference_time": "2026-04-18T21:00:00",
                "streamflow_m3s": 0.41,
                "method": "kerchunk",
            },
            {
                "forecast_date": "2026-04-19",
                "forecast_cycle": 0,
                "product": "short_range",
                "domain": "conus",
                "lead_hour": 1,
                "feature_id": 3586192,
                "valid_time": "2026-04-19T01:00:00",
                "reference_time": "2026-04-19T00:00:00",
                "streamflow_m3s": 0.40,
                "method": "kerchunk",
            },
        ],
        columns=SERIES_COLUMNS,
    )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        Mock(
            return_value=frame
        ),
    )

    output = tmp_path / "with-t0.csv"

    assert main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "1",
        "--no-cache",
        "--out", str(output),
    ]) == 0

    exported = pd.read_csv(
        output
    )

    assert exported.loc[
        exported["lead_hour"].eq(0),
        "reference_time",
    ].iloc[0] == "2026-04-18T21:00:00"

    _, manifest = _load_manifest(
        output
    )

    assert manifest[
        "output_contract"
    ]["reference_time"] == (
        "literal source reference-time metadata"
    )
