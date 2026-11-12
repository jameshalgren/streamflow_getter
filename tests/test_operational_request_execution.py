"""Tests for execution of planned operational NWM requests."""

from datetime import date, datetime, timedelta
from unittest.mock import Mock, call

import pandas as pd
import pytest

from streamflow_getter.operational_nwm import ForecastConfig
from streamflow_getter.operational_requests import (
    fetch_operational_configs,
)
from streamflow_getter.request_planning import (
    plan_operational_configs,
)


def _frame(
    config,
    reaches,
    lead_hour,
    *,
    include_t0,
):
    cycle_time = datetime.combine(
        date.fromisoformat(config.date),
        datetime.min.time(),
    ).replace(hour=config.cycle)

    rows = []

    if include_t0:
        for reach in reaches:
            rows.append({
                "forecast_date": config.date,
                "forecast_cycle": config.cycle,
                "product": config.spec.analysis_product,
                "domain": config.domain,
                "lead_hour": 0,
                "feature_id": reach,
                "valid_time": cycle_time.isoformat(),
                "reference_time": cycle_time.isoformat(),
                "streamflow_m3s": 0.4,
                "method": "kerchunk",
            })

    for reach in reaches:
        rows.append({
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": config.product,
            "domain": config.domain,
            "lead_hour": lead_hour,
            "feature_id": reach,
            "valid_time": (
                cycle_time
                + timedelta(hours=lead_hour)
            ).isoformat(),
            "reference_time": cycle_time.isoformat(),
            "streamflow_m3s": 0.5,
            "method": "kerchunk",
        })

    return pd.DataFrame(rows)


def test_executor_reuses_shared_analysis_t0(
    monkeypatch,
    tmp_path,
):
    from streamflow_getter import operational_nwm

    configs = plan_operational_configs(
        "2026-04-19",
        "2026-04-19",
        cycles=(0,),
        products=(
            "short_range",
            "medium_range_mem1",
            "medium_range_mem2",
            "medium_range_no_da",
        ),
    )

    calls = []

    def fake_fetch(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0=True,
        cache_dir=None,
    ):
        calls.append(
            (
                config.product,
                include_t0,
                tuple(reach_ids),
                cache_dir,
            )
        )

        return _frame(
            config,
            reach_ids,
            3,
            include_t0=include_t0,
        )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fake_fetch,
    )

    result = fetch_operational_configs(
        configs,
        [3586192],
        3,
        3,
        include_t0=True,
        cache_dir=tmp_path,
    )

    assert calls == [
        ("short_range", True, (3586192,), tmp_path),
        ("medium_range_mem1", False, (3586192,), tmp_path),
        ("medium_range_mem2", False, (3586192,), tmp_path),
        ("medium_range_no_da", True, (3586192,), tmp_path),
    ]

    assert len(result) == 8

    t0 = result.loc[result["lead_hour"].eq(0)]

    assert list(t0["requested_product"]) == [
        "short_range",
        "medium_range_mem1",
        "medium_range_mem2",
        "medium_range_no_da",
    ]

    assert list(t0["product"]) == [
        "analysis_assim",
        "analysis_assim",
        "analysis_assim",
        "analysis_assim_no_da",
    ]

    forecasts = result.loc[result["lead_hour"].eq(3)]

    assert (
        forecasts["requested_product"]
        == forecasts["product"]
    ).all()


def test_executor_omits_t0_when_requested(
    monkeypatch,
):
    from streamflow_getter import operational_nwm

    configs = plan_operational_configs(
        "2026-04-19",
        "2026-04-19",
        cycles=(0,),
        products=(
            "short_range",
            "medium_range_mem1",
        ),
    )

    calls = []

    def fake_fetch(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0=True,
        cache_dir=None,
    ):
        calls.append(
            (config.product, include_t0)
        )

        return _frame(
            config,
            reach_ids,
            3,
            include_t0=include_t0,
        )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fake_fetch,
    )

    result = fetch_operational_configs(
        configs,
        [3586192],
        3,
        3,
        include_t0=False,
    )

    assert calls == [
        ("short_range", False),
        ("medium_range_mem1", False),
    ]

    assert not result["lead_hour"].eq(0).any()
    assert list(result["requested_product"]) == [
        "short_range",
        "medium_range_mem1",
    ]


def test_executor_materializes_reach_generator_for_every_config(
    monkeypatch,
):
    from streamflow_getter import operational_nwm

    configs = plan_operational_configs(
        "2026-04-19",
        "2026-04-20",
    )

    captured = []

    def fake_fetch(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0=True,
        cache_dir=None,
    ):
        captured.append(tuple(reach_ids))

        return _frame(
            config,
            reach_ids,
            1,
            include_t0=include_t0,
        )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fake_fetch,
    )

    reaches = (
        reach
        for reach in [3586192, 3586194]
    )

    result = fetch_operational_configs(
        configs,
        reaches,
        1,
        1,
    )

    assert captured == [
        (3586192, 3586194),
        (3586192, 3586194),
    ]

    assert set(result["feature_id"]) == {
        3586192,
        3586194,
    }


def test_executor_validates_all_lead_windows_before_retrieval(
    monkeypatch,
):
    from streamflow_getter import operational_nwm

    configs = [
        ForecastConfig(
            product="short_range",
        ),
        ForecastConfig(
            product="long_range_mem1",
        ),
    ]

    fetch = Mock(
        side_effect=AssertionError(
            "Retrieval started before complete validation"
        )
    )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fetch,
    )

    with pytest.raises(
        ValueError,
        match="No available forecast leads",
    ):
        fetch_operational_configs(
            configs,
            [3586192],
            1,
            2,
        )

    fetch.assert_not_called()


def test_executor_rejects_duplicate_configs_before_retrieval(
    monkeypatch,
):
    from streamflow_getter import operational_nwm

    config = ForecastConfig()

    fetch = Mock(
        side_effect=AssertionError(
            "Retrieval started for duplicate configs"
        )
    )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fetch,
    )

    with pytest.raises(
        ValueError,
        match="Duplicate operational forecast configurations",
    ):
        fetch_operational_configs(
            [config, config],
            [3586192],
            1,
            1,
        )

    fetch.assert_not_called()


@pytest.mark.parametrize(
    "configs,error_type,message",
    [
        ([], ValueError, "At least one forecast configuration"),
        (
            [ForecastConfig(), object()],
            TypeError,
            "ForecastConfig",
        ),
    ],
)
def test_executor_rejects_invalid_config_collections(
    monkeypatch,
    configs,
    error_type,
    message,
):
    from streamflow_getter import operational_nwm

    fetch = Mock()

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fetch,
    )

    with pytest.raises(
        error_type,
        match=message,
    ):
        fetch_operational_configs(
            configs,
            [3586192],
            1,
            1,
        )

    fetch.assert_not_called()


def test_executor_strict_failure_propagates_and_stops(
    monkeypatch,
):
    from streamflow_getter import operational_nwm

    configs = plan_operational_configs(
        "2026-04-19",
        "2026-04-21",
    )

    failure = OSError(
        "Controlled second-configuration failure"
    )

    calls = []

    def fake_fetch(
        config,
        reach_ids,
        start_hour,
        end_hour,
        *,
        include_t0=True,
        cache_dir=None,
    ):
        calls.append(config.date)

        if len(calls) == 2:
            raise failure

        if len(calls) > 2:
            raise AssertionError(
                "Execution continued after failure"
            )

        return _frame(
            config,
            reach_ids,
            1,
            include_t0=include_t0,
        )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fake_fetch,
    )

    with pytest.raises(OSError) as caught:
        fetch_operational_configs(
            configs,
            [3586192],
            1,
            1,
        )

    assert caught.value is failure
    assert calls == [
        "2026-04-19",
        "2026-04-20",
    ]


def test_executor_rejects_wrong_returned_identity(
    monkeypatch,
):
    from streamflow_getter import operational_nwm

    config = ForecastConfig()

    frame = _frame(
        config,
        [3586192],
        1,
        include_t0=False,
    )

    frame["forecast_date"] = "2026-04-20"

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        Mock(return_value=frame),
    )

    with pytest.raises(
        ValueError,
        match="unexpected forecast date",
    ):
        fetch_operational_configs(
            [config],
            [3586192],
            1,
            1,
            include_t0=False,
        )
