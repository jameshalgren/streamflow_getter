"""Tests for stable operational output and run-provenance contracts."""

import json

import pandas as pd
import pytest

from streamflow_getter.operational_nwm import ForecastConfig
from streamflow_getter.operational_provenance import (
    COMBINED_OPERATIONAL_COLUMNS,
    COMBINED_ROW_IDENTITY,
    MANIFEST_SCHEMA_VERSION,
    OPERATIONAL_SERIES_COLUMNS,
    build_operational_run_manifest,
    expected_combined_row_identities,
    validate_combined_operational_frame,
)


def _configs():
    return [
        ForecastConfig(
            date="2026-04-19",
            cycle=0,
            product="medium_range_mem1",
        ),
        ForecastConfig(
            date="2026-04-19",
            cycle=0,
            product="medium_range_mem2",
        ),
    ]


def _combined_frame():
    return pd.DataFrame(
        [
            {
                "forecast_date": "2026-04-19",
                "forecast_cycle": 0,
                "requested_product": "medium_range_mem1",
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
                "requested_product": "medium_range_mem1",
                "product": "medium_range_mem1",
                "domain": "conus",
                "lead_hour": 3,
                "feature_id": 3586192,
                "valid_time": "2026-04-19T03:00:00",
                "reference_time": "2026-04-19T00:00:00",
                "streamflow_m3s": 0.39,
                "method": "kerchunk",
            },
            {
                "forecast_date": "2026-04-19",
                "forecast_cycle": 0,
                "requested_product": "medium_range_mem2",
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
                "requested_product": "medium_range_mem2",
                "product": "medium_range_mem2",
                "domain": "conus",
                "lead_hour": 3,
                "feature_id": 3586192,
                "valid_time": "2026-04-19T03:00:00",
                "reference_time": "2026-04-19T00:00:00",
                "streamflow_m3s": 0.39,
                "method": "native_remote",
            },
        ],
        columns=COMBINED_OPERATIONAL_COLUMNS,
    )


def test_column_contracts_are_explicit_and_distinct():
    assert OPERATIONAL_SERIES_COLUMNS == (
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
    )

    assert COMBINED_OPERATIONAL_COLUMNS == (
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
    )

    assert COMBINED_ROW_IDENTITY == (
        "forecast_date",
        "forecast_cycle",
        "requested_product",
        "domain",
        "lead_hour",
        "feature_id",
    )


def test_combined_contract_accepts_literal_analysis_source_time():
    frame = _combined_frame()

    validate_combined_operational_frame(
        frame
    )

    assert (
        frame.loc[
            frame["lead_hour"].eq(0),
            "reference_time",
        ]
        .eq("2026-04-18T21:00:00")
        .all()
    )


def test_expected_identity_uses_requested_product_for_t0():
    identities = expected_combined_row_identities(
        _configs(),
        [3586192],
        3,
        3,
        include_t0=True,
    )

    assert identities == [
        (
            "2026-04-19",
            0,
            "medium_range_mem1",
            "conus",
            0,
            3586192,
        ),
        (
            "2026-04-19",
            0,
            "medium_range_mem1",
            "conus",
            3,
            3586192,
        ),
        (
            "2026-04-19",
            0,
            "medium_range_mem2",
            "conus",
            0,
            3586192,
        ),
        (
            "2026-04-19",
            0,
            "medium_range_mem2",
            "conus",
            3,
            3586192,
        ),
    ]


def test_manifest_records_complete_strict_run():
    manifest = build_operational_run_manifest(
        _combined_frame(),
        _configs(),
        [3586192],
        3,
        3,
        include_t0=True,
        selection={
            "mode": "event",
            "name": "Alabama April 2026",
            "resolved_start_date": "2026-04-19",
            "resolved_end_date": "2026-04-19",
        },
        cache_policy={
            "mode": "persistent",
            "directory": "~/.cache/streamflow_getter",
        },
        software={
            "streamflow_getter_commit": "2842ed0",
        },
        diagnostics={
            "fallback_policy": "strict",
        },
        created_utc="2026-11-11T20:00:00-06:00",
    )

    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["status"] == "complete"

    assert manifest["created_utc"] == (
        "2026-11-12T02:00:00+00:00"
    )

    assert manifest["selection"]["mode"] == "event"
    assert manifest["selection"]["name"] == (
        "Alabama April 2026"
    )

    assert manifest["request"]["reach_ids"] == [
        3586192
    ]

    assert manifest["result"]["row_count"] == 4

    assert manifest["result"]["requested_product_counts"] == {
        "medium_range_mem1": 2,
        "medium_range_mem2": 2,
    }

    assert manifest["result"]["source_product_counts"] == {
        "analysis_assim": 2,
        "medium_range_mem1": 1,
        "medium_range_mem2": 1,
    }

    assert manifest["result"]["method_counts"] == {
        "kerchunk": 3,
        "native_remote": 1,
    }

    assert manifest["completeness"] == {
        "mode": "strict",
        "expected_row_count": 4,
        "actual_row_count": 4,
        "missing_row_count": 0,
        "extra_row_count": 0,
        "complete": True,
    }

    assert manifest["failures"] == []

    json.dumps(
        manifest,
        sort_keys=True,
    )


def test_manifest_rejects_missing_expected_row():
    frame = _combined_frame().iloc[:-1].copy()

    with pytest.raises(
        ValueError,
        match="missing=1, extra=0",
    ):
        build_operational_run_manifest(
            frame,
            _configs(),
            [3586192],
            3,
            3,
        )


def test_manifest_rejects_unplanned_extra_row():
    frame = _combined_frame()

    extra = frame.iloc[[1]].copy()
    extra["feature_id"] = 9999999

    frame = pd.concat(
        [frame, extra],
        ignore_index=True,
    )

    with pytest.raises(
        ValueError,
        match="missing=0, extra=1",
    ):
        build_operational_run_manifest(
            frame,
            _configs(),
            [3586192],
            3,
            3,
        )


def test_contract_rejects_duplicate_row_identity():
    frame = pd.concat(
        [
            _combined_frame(),
            _combined_frame().iloc[[0]],
        ],
        ignore_index=True,
    )

    with pytest.raises(
        ValueError,
        match="Duplicate combined operational row identity",
    ):
        validate_combined_operational_frame(
            frame
        )


def test_contract_rejects_forecast_source_product_mismatch():
    frame = _combined_frame()

    frame.loc[
        frame["lead_hour"].eq(3),
        "product",
    ] = "short_range"

    with pytest.raises(
        ValueError,
        match="differs from requested product",
    ):
        validate_combined_operational_frame(
            frame
        )


def test_contract_rejects_column_drift():
    frame = _combined_frame()
    frame["fallback_reason"] = ""

    with pytest.raises(
        ValueError,
        match="stable contract",
    ):
        validate_combined_operational_frame(
            frame
        )


@pytest.mark.parametrize(
    "field,value",
    [
        (
            "selection",
            {"not_json": object()},
        ),
        (
            "cache_policy",
            {"not_json": object()},
        ),
        (
            "software",
            {"not_json": object()},
        ),
        (
            "diagnostics",
            {"not_json": object()},
        ),
    ],
)
def test_manifest_rejects_non_json_provenance(
    field,
    value,
):
    kwargs = {
        "selection": {},
        "cache_policy": {},
        "software": {},
        "diagnostics": {},
    }

    kwargs[field] = value

    with pytest.raises(
        ValueError,
        match=field,
    ):
        build_operational_run_manifest(
            _combined_frame(),
            _configs(),
            [3586192],
            3,
            3,
            created_utc="2026-11-12T02:00:00Z",
            **kwargs,
        )


def test_manifest_rejects_naive_created_timestamp():
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        build_operational_run_manifest(
            _combined_frame(),
            _configs(),
            [3586192],
            3,
            3,
            created_utc="2026-11-11T20:00:00",
        )

def test_manifest_records_derived_nwm_version():
    manifest = build_operational_run_manifest(
        _combined_frame(),
        _configs(),
        [3586192],
        3,
        3,
        created_utc="2026-11-12T02:00:00Z",
    )

    assert manifest["model"] == {
        "name": "National Water Model",
        "version_basis": "forecast_initialization_utc",
        "operational_versions": ["3.0"],
        "unresolved_config_count": 0,
    }

    assert {
        config["nwm_version"]
        for config in manifest["request"]["configs"]
    } == {"3.0"}


def test_manifest_can_record_request_crossing_v31_boundary():
    configs = [
        ForecastConfig(
            date="2026-08-18",
            cycle=11,
            product="short_range",
        ),
        ForecastConfig(
            date="2026-08-18",
            cycle=12,
            product="short_range",
        ),
    ]

    rows = []

    for config in configs:
        reference_hour = config.cycle
        valid_hour = config.cycle + 1

        rows.append({
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "requested_product": config.product,
            "product": config.product,
            "domain": config.domain,
            "lead_hour": 1,
            "feature_id": 3586192,
            "valid_time": (
                f"{config.date}T"
                f"{valid_hour:02d}:00:00"
            ),
            "reference_time": (
                f"{config.date}T"
                f"{reference_hour:02d}:00:00"
            ),
            "streamflow_m3s": 0.41,
            "method": "kerchunk",
        })

    frame = pd.DataFrame(
        rows,
        columns=COMBINED_OPERATIONAL_COLUMNS,
    )

    manifest = build_operational_run_manifest(
        frame,
        configs,
        [3586192],
        1,
        1,
        include_t0=False,
        created_utc="2026-11-12T02:00:00Z",
    )

    assert manifest["model"]["operational_versions"] == [
        "3.0",
        "3.1",
    ]

    assert manifest["model"]["unresolved_config_count"] == 0

    assert [
        config["nwm_version"]
        for config in manifest["request"]["configs"]
    ] == [
        "3.0",
        "3.1",
    ]
