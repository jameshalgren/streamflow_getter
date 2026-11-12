"""Tests for operational NWM version provenance."""

from datetime import datetime, timezone

import pytest

from streamflow_getter.operational_nwm import ForecastConfig
from streamflow_getter.operational_versions import (
    OPERATIONAL_VERSION_TRANSITIONS,
    forecast_initialization_utc,
    resolve_operational_nwm_version,
)


def test_initialization_is_timezone_aware_utc():
    config = ForecastConfig(
        date="2026-08-18",
        cycle=12,
    )

    assert forecast_initialization_utc(
        config
    ) == datetime(
        2026,
        8,
        18,
        12,
        tzinfo=timezone.utc,
    )


@pytest.mark.parametrize(
    "date_value,cycle,expected",
    [
        ("2018-01-01", 0, "1.1"),
        ("2018-03-06", 11, "1.1"),
        ("2018-03-06", 12, "1.2"),
        ("2019-06-19", 11, "1.2"),
        ("2019-06-19", 12, "2.0"),
        ("2021-04-20", 11, "2.0"),
        ("2021-04-20", 12, "2.1"),
        ("2023-09-20", 11, "2.1"),
        ("2023-09-20", 12, "3.0"),
        ("2026-04-19", 0, "3.0"),
        ("2026-08-18", 11, "3.0"),
        ("2026-08-18", 12, "3.1"),
        ("2026-11-10", 0, "3.1"),
    ],
)
def test_resolve_operational_version_boundaries(
    date_value,
    cycle,
    expected,
):
    assert resolve_operational_nwm_version(
        ForecastConfig(
            date=date_value,
            cycle=cycle,
        )
    ) == expected


def test_dates_before_project_version_baseline_are_unresolved():
    assert resolve_operational_nwm_version(
        ForecastConfig(
            date="2017-12-31",
            cycle=23,
        )
    ) is None


def test_transition_registry_is_ordered_and_verified():
    assert [
        transition.version
        for transition
        in OPERATIONAL_VERSION_TRANSITIONS
    ] == [
        "1.2",
        "2.0",
        "2.1",
        "3.0",
        "3.1",
    ]

    assert [
        transition.notice
        for transition
        in OPERATIONAL_VERSION_TRANSITIONS
    ] == [
        "NWS SCN18-16",
        "NWS SCN19-42",
        "NWS SCN20-119",
        "NWS SCN23-76",
        "NWS SCN26-64",
    ]

    effective = [
        transition.effective_utc
        for transition
        in OPERATIONAL_VERSION_TRANSITIONS
    ]

    assert effective == sorted(
        effective
    )


def test_version_resolution_rejects_non_config():
    with pytest.raises(
        TypeError,
        match="ForecastConfig",
    ):
        resolve_operational_nwm_version(
            object()
        )
