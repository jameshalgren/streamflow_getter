
"""Tests for operational NWM forecast time-series assembly."""

import pytest

from streamflow_getter import operational_nwm
from streamflow_getter.operational_nwm import (
    ForecastConfig,
    fetch_operational_series,
)


def test_series_includes_analysis_t0(monkeypatch):
    config = ForecastConfig()

    def fake_fetch(config, hour, reach_ids):
        assert reach_ids == [3586192]

        return {
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": "analysis_assim" if hour == 0 else "short_range",
            "domain": config.domain,
            "lead_hour": hour,
            "method": "kerchunk",
            "valid_time": (
                f"2026-04-19T{hour:02d}:00:00"
            ),
            "reference_time": (
                "2026-04-18T21:00:00"
                if hour == 0
                else "2026-04-19T00:00:00"
            ),
            "streamflow_m3s": {3586192: 0.41 + hour},
        }

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_forecast",
        fake_fetch,
    )

    frame = fetch_operational_series(
        config,
        [3586192],
        1,
        2,
    )

    assert list(frame["lead_hour"]) == [0, 1, 2]
    assert list(frame["product"]) == [
        "analysis_assim",
        "short_range",
        "short_range",
    ]

    assert frame.iloc[0]["reference_time"] == (
        "2026-04-18T21:00:00"
    )
    assert frame.iloc[1]["reference_time"] == (
        "2026-04-19T00:00:00"
    )


def test_series_without_t0(monkeypatch):
    config = ForecastConfig()

    def fake_fetch(config, hour, reach_ids):
        assert hour > 0

        return {
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": "short_range",
            "domain": config.domain,
            "lead_hour": hour,
            "method": "kerchunk",
            "valid_time": f"2026-04-19T{hour:02d}:00:00",
            "reference_time": "2026-04-19T00:00:00",
            "streamflow_m3s": {3586192: 0.41},
        }

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_forecast",
        fake_fetch,
    )

    frame = fetch_operational_series(
        config,
        [3586192],
        1,
        2,
        include_t0=False,
    )

    assert list(frame["lead_hour"]) == [1, 2]


@pytest.mark.parametrize(
    "start,end",
    [
        (0, 2),
        (2, 1),
        (-1, 2),
        (1.5, 2),
        (1, True),
    ],
)
def test_invalid_forecast_range(start, end):
    with pytest.raises(ValueError):
        fetch_operational_series(
            ForecastConfig(),
            [3586192],
            start,
            end,
        )



@pytest.mark.parametrize(
    "field,invalid_value,error",
    [
        ("forecast_date", "2026-04-20", "forecast date"),
        ("forecast_cycle", 12, "forecast cycle"),
        ("domain", "alaska", "NWM domain"),
        ("valid_time", "2026-04-19T03:00:00", "valid time"),
        ("reference_time", "2026-04-19T03:00:00", "reference time"),
    ],
)
def test_series_rejects_inconsistent_forecast(
    monkeypatch, field, invalid_value, error
):
    config = ForecastConfig()

    def fake_fetch(config, hour, reach_ids):
        result = {
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": "short_range",
            "domain": config.domain,
            "lead_hour": hour,
            "method": "kerchunk",
            "valid_time": "2026-04-19T01:00:00",
            "reference_time": "2026-04-19T00:00:00",
            "streamflow_m3s": {3586192: 0.41},
        }

        result[field] = invalid_value
        return result

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_forecast",
        fake_fetch,
    )

    with pytest.raises(ValueError, match=error):
        fetch_operational_series(
            config,
            [3586192],
            1,
            1,
            include_t0=False,
        )


@pytest.mark.parametrize("invalid_flow", [float("nan"), float("inf")])
def test_series_rejects_nonfinite_streamflow(
    monkeypatch, invalid_flow
):
    config = ForecastConfig()

    def fake_fetch(config, hour, reach_ids):
        return {
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": "short_range",
            "domain": config.domain,
            "lead_hour": hour,
            "method": "kerchunk",
            "valid_time": "2026-04-19T01:00:00",
            "reference_time": "2026-04-19T00:00:00",
            "streamflow_m3s": {3586192: invalid_flow},
        }

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_forecast",
        fake_fetch,
    )

    with pytest.raises(ValueError, match="Non-finite"):
        fetch_operational_series(
            config,
            [3586192],
            1,
            1,
            include_t0=False,
        )

@pytest.mark.parametrize(
    "reach_ids",
    [
        [0],
        [-1],
        [3586192.5],
        ["3586192"],
        [True],
    ],
)
def test_series_rejects_invalid_reach_ids(
    monkeypatch, reach_ids
):
    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_forecast",
        unexpected_fetch,
    )

    with pytest.raises(ValueError, match="positive integers"):
        fetch_operational_series(
            ForecastConfig(),
            reach_ids,
            1,
            1,
        )
