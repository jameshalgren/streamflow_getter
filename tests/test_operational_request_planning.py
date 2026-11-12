"""Tests for pure operational NWM request planning."""

import pytest

from streamflow_getter.operational_nwm import ForecastConfig
from streamflow_getter.request_planning import (
    OperationalEvent,
    plan_operational_configs,
    plan_operational_event,
    resolve_recent_date_range,
)


def test_plan_single_day_preserves_current_default_request():
    configs = plan_operational_configs(
        "2026-04-19",
        "2026-04-19",
    )

    assert configs == [
        ForecastConfig(
            date="2026-04-19",
            cycle=0,
            product="short_range",
            domain="conus",
        )
    ]


def test_plan_date_range_is_inclusive():
    configs = plan_operational_configs(
        "2026-04-19",
        "2026-04-21",
    )

    assert [config.date for config in configs] == [
        "2026-04-19",
        "2026-04-20",
        "2026-04-21",
    ]


def test_plan_multiple_cycles_and_products_in_deterministic_order():
    configs = plan_operational_configs(
        "2026-04-19",
        "2026-04-20",
        cycles=(0, 6),
        products=(
            "short_range",
            "medium_range_mem1",
        ),
    )

    assert [
        (config.date, config.cycle, config.product)
        for config in configs
    ] == [
        ("2026-04-19", 0, "short_range"),
        ("2026-04-19", 0, "medium_range_mem1"),
        ("2026-04-19", 6, "short_range"),
        ("2026-04-19", 6, "medium_range_mem1"),
        ("2026-04-20", 0, "short_range"),
        ("2026-04-20", 0, "medium_range_mem1"),
        ("2026-04-20", 6, "short_range"),
        ("2026-04-20", 6, "medium_range_mem1"),
    ]


def test_plan_accepts_finite_generators():
    cycles = (cycle for cycle in [0, 6])
    products = (
        product
        for product in ["short_range", "medium_range_mem1"]
    )

    configs = plan_operational_configs(
        "2026-04-19",
        "2026-04-19",
        cycles=cycles,
        products=products,
    )

    assert len(configs) == 4


@pytest.mark.parametrize(
    "start_date,end_date,message",
    [
        ("2026-04-32", "2026-05-01", "start_date"),
        ("2026-04-19", "2026-02-30", "end_date"),
        ("2026-4-19", "2026-04-20", "start_date"),
        ("2026-04-21", "2026-04-19", "must not precede"),
    ],
)
def test_plan_rejects_invalid_date_ranges(
    start_date,
    end_date,
    message,
):
    with pytest.raises(ValueError, match=message):
        plan_operational_configs(
            start_date,
            end_date,
        )


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"cycles": ()}, "At least one forecast cycle"),
        ({"products": ()}, "At least one forecast product"),
        ({"cycles": (0, 0)}, "Duplicate forecast cycles"),
        (
            {"products": ("short_range", "short_range")},
            "Duplicate forecast products",
        ),
        ({"cycles": (True,)}, "Forecast cycles must be integers"),
        ({"products": ("",)}, "nonempty strings"),
    ],
)
def test_plan_rejects_invalid_selection_collections(
    kwargs,
    message,
):
    with pytest.raises(ValueError, match=message):
        plan_operational_configs(
            "2026-04-19",
            "2026-04-19",
            **kwargs,
        )


def test_plan_rejects_incompatible_cycle_product_combination():
    with pytest.raises(
        ValueError,
        match=(
            "date=2026-04-19, cycle=1, "
            "product='medium_range_mem1'"
        ),
    ) as caught:
        plan_operational_configs(
            "2026-04-19",
            "2026-04-19",
            cycles=(1,),
            products=("medium_range_mem1",),
        )

    assert isinstance(caught.value.__cause__, ValueError)
    assert "Unsupported cycle" in str(caught.value.__cause__)


def test_plan_performs_no_remote_access(monkeypatch):
    from streamflow_getter import operational_nwm

    def unexpected_remote_access(*args, **kwargs):
        raise AssertionError("Planner attempted remote retrieval")

    monkeypatch.setattr(
        operational_nwm,
        "prepare_operational_reference",
        unexpected_remote_access,
    )
    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_forecast",
        unexpected_remote_access,
    )
    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_remote_access,
    )

    configs = plan_operational_configs(
        "2026-04-19",
        "2026-04-21",
        cycles=(0,),
        products=("short_range",),
    )

    assert len(configs) == 3

def test_recent_date_range_includes_as_of_date():
    assert resolve_recent_date_range(
        1,
        as_of="2026-04-21",
    ) == (
        "2026-04-21",
        "2026-04-21",
    )

    assert resolve_recent_date_range(
        3,
        as_of="2026-04-21",
    ) == (
        "2026-04-19",
        "2026-04-21",
    )


@pytest.mark.parametrize(
    "days",
    [0, -1, True, 1.5],
)
def test_recent_date_range_rejects_invalid_day_count(days):
    with pytest.raises(
        ValueError,
        match="positive integer",
    ):
        resolve_recent_date_range(
            days,
            as_of="2026-04-21",
        )


def test_recent_date_range_rejects_invalid_as_of_date():
    with pytest.raises(
        ValueError,
        match="as_of",
    ):
        resolve_recent_date_range(
            3,
            as_of="2026-02-30",
        )

def test_operational_event_preserves_name_and_absolute_dates():
    event = OperationalEvent(
        name="Alabama April 2026",
        start_date="2026-04-19",
        end_date="2026-04-21",
    )

    assert event.name == "Alabama April 2026"
    assert event.start_date == "2026-04-19"
    assert event.end_date == "2026-04-21"


def test_plan_operational_event_reuses_standard_planner_order():
    event = OperationalEvent(
        name="Alabama April 2026",
        start_date="2026-04-19",
        end_date="2026-04-20",
    )

    configs = plan_operational_event(
        event,
        cycles=(0, 6),
        products=(
            "short_range",
            "medium_range_mem1",
        ),
    )

    assert [
        (
            config.date,
            config.cycle,
            config.product,
        )
        for config in configs
    ] == [
        ("2026-04-19", 0, "short_range"),
        ("2026-04-19", 0, "medium_range_mem1"),
        ("2026-04-19", 6, "short_range"),
        ("2026-04-19", 6, "medium_range_mem1"),
        ("2026-04-20", 0, "short_range"),
        ("2026-04-20", 0, "medium_range_mem1"),
        ("2026-04-20", 6, "short_range"),
        ("2026-04-20", 6, "medium_range_mem1"),
    ]


@pytest.mark.parametrize(
    "kwargs,message",
    [
        (
            {
                "name": "",
                "start_date": "2026-04-19",
                "end_date": "2026-04-21",
            },
            "event name",
        ),
        (
            {
                "name": "   ",
                "start_date": "2026-04-19",
                "end_date": "2026-04-21",
            },
            "event name",
        ),
        (
            {
                "name": "Invalid start",
                "start_date": "2026-02-30",
                "end_date": "2026-04-21",
            },
            "event start_date",
        ),
        (
            {
                "name": "Invalid end",
                "start_date": "2026-04-19",
                "end_date": "2026-02-30",
            },
            "event end_date",
        ),
        (
            {
                "name": "Reverse",
                "start_date": "2026-04-21",
                "end_date": "2026-04-19",
            },
            "must not precede",
        ),
    ],
)
def test_operational_event_rejects_invalid_metadata(
    kwargs,
    message,
):
    with pytest.raises(
        ValueError,
        match=message,
    ):
        OperationalEvent(**kwargs)


def test_plan_operational_event_rejects_wrong_type():
    with pytest.raises(
        TypeError,
        match="OperationalEvent",
    ):
        plan_operational_event(
            {
                "name": "not an event",
                "start_date": "2026-04-19",
                "end_date": "2026-04-21",
            }
        )


def test_event_planning_retains_standard_configuration_validation():
    event = OperationalEvent(
        name="Invalid medium cycle",
        start_date="2026-04-19",
        end_date="2026-04-19",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported cycle",
    ):
        plan_operational_event(
            event,
            cycles=(1,),
            products=("medium_range_mem1",),
        )


def test_event_is_immutable():
    event = OperationalEvent(
        name="Immutable",
        start_date="2026-04-19",
        end_date="2026-04-21",
    )

    with pytest.raises(
        AttributeError,
    ):
        event.name = "Changed"
