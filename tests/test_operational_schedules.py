
"""Tests for operational NWM forecast lead schedules."""

import pytest

from streamflow_getter.operational_nwm import (
    ForecastConfig,
    PRODUCT_SPECS,
    ProductSpec,
    fetch_operational_series,
)


@pytest.fixture
def schedule_config(monkeypatch):
    """Construct temporary product configurations without changing files."""

    def make_config(step, max_hour=240):
        product = f"test_schedule_{step}"

        monkeypatch.setitem(
            PRODUCT_SPECS,
            product,
            ProductSpec(
                directory=product,
                filename_product=product,
                channel_family="channel_rt",
                cycles=(0, 6, 12, 18),
                max_hour=max_hour,
                lead_step_hours=step,
            ),
        )

        return ForecastConfig(
            date="2026-04-19",
            cycle=0,
            product=product,
        )

    return make_config


@pytest.mark.parametrize(
    "step,start,end,expected",
    [
        (1, 1, 5, [1, 2, 3, 4, 5]),
        (3, 3, 12, [3, 6, 9, 12]),
        (3, 4, 12, [6, 9, 12]),
        (6, 6, 24, [6, 12, 18, 24]),
        (6, 7, 20, [12, 18]),
        (3, 6, 6, [6]),
        (6, 12, 12, [12]),
    ],
)
def test_forecast_hours_selects_available_leads(
    schedule_config, step, start, end, expected
):
    config = schedule_config(step)
    assert config.forecast_hours(start, end) == expected


@pytest.mark.parametrize(
    "step,start,end",
    [
        (3, 4, 5),
        (6, 7, 11),
        (3, 1, 2),
        (6, 1, 5),
    ],
)
def test_forecast_hours_rejects_empty_windows(
    schedule_config, step, start, end
):
    config = schedule_config(step)

    with pytest.raises(ValueError, match="No available forecast leads"):
        config.forecast_hours(start, end)


@pytest.mark.parametrize(
    "step,hour",
    [
        (3, 1),
        (3, 4),
        (3, 5),
        (6, 1),
        (6, 7),
        (6, 11),
    ],
)
def test_filename_rejects_unavailable_leads(
    schedule_config, step, hour
):
    config = schedule_config(step)

    with pytest.raises(ValueError, match="multiple"):
        config.filename(hour)


@pytest.mark.parametrize(
    "step,hour",
    [
        (3, 3),
        (3, 6),
        (3, 240),
        (6, 6),
        (6, 12),
        (6, 240),
    ],
)
def test_filename_accepts_available_leads(
    schedule_config, step, hour
):
    config = schedule_config(step)

    assert f".f{hour:03d}.conus.nc" in config.filename(hour)


@pytest.mark.parametrize(
    "start,end",
    [
        (0, 12),
        (12, 6),
        (-1, 12),
    ],
)
def test_forecast_hours_rejects_invalid_ranges(
    schedule_config, start, end
):
    config = schedule_config(3)

    with pytest.raises(ValueError, match="Invalid forecast hour range"):
        config.forecast_hours(start, end)


@pytest.mark.parametrize(
    "start,end",
    [
        (True, 12),
        (3, False),
        (3.0, 12),
        (3, 12.0),
    ],
)
def test_forecast_hours_rejects_noninteger_boundaries(
    schedule_config, start, end
):
    config = schedule_config(3)

    with pytest.raises(ValueError, match="integers"):
        config.forecast_hours(start, end)


def test_forecast_hours_rejects_excessive_end_hour(schedule_config):
    config = schedule_config(3, max_hour=240)

    with pytest.raises(ValueError, match="Forecast hour"):
        config.forecast_hours(3, 241)


@pytest.mark.parametrize("step", [0, -1, True, 1.5])
def test_forecast_hours_rejects_invalid_step(schedule_config, step):
    config = schedule_config(step)

    with pytest.raises(ValueError, match="positive integer"):
        config.forecast_hours(1, 12)


def test_existing_short_range_schedule_unchanged():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="short_range",
    )

    assert config.forecast_hours(1, 18) == list(range(1, 19))


def test_existing_medium_range_schedule_unchanged():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_mem1",
    )

    assert config.forecast_hours(1, 240) == list(range(1, 241))


def test_series_retrieves_only_available_three_hour_leads(
    schedule_config, monkeypatch
):
    """Fetch only scheduled forecast hours, including analysis t0."""
    import numpy as np
    import streamflow_getter.operational_nwm as operational

    config = schedule_config(3)
    requested_hours = []

    def fake_fetch(config, hour, reach_ids, *, cache_dir=None):
        requested_hours.append(hour)

        cycle_time = np.datetime64("2026-04-19T00:00:00", "s")
        valid_time = cycle_time + np.timedelta64(hour, "h")

        return {
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": (
                "analysis_assim" if hour == 0 else config.product
            ),
            "domain": config.domain,
            "lead_hour": hour,
            "method": "kerchunk",
            "valid_time": str(valid_time),
            "reference_time": str(cycle_time),
            "streamflow_m3s": {3586192: 0.41},
        }

    monkeypatch.setattr(
        operational,
        "fetch_operational_forecast",
        fake_fetch,
    )

    frame = operational.fetch_operational_series(
        config,
        [3586192],
        start_hour=4,
        end_hour=12,
        include_t0=True,
    )

    assert requested_hours == [0, 6, 9, 12]
    assert frame["lead_hour"].tolist() == [0, 6, 9, 12]
    assert frame["product"].tolist() == [
        "analysis_assim",
        config.product,
        config.product,
        config.product,
    ]
