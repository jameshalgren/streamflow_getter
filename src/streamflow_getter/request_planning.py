"""Pure request planning for operational NWM forecast initializations."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from streamflow_getter.operational_nwm import ForecastConfig


@dataclass(frozen=True)
class OperationalEvent:
    """Name an absolute UTC calendar-date window for later retrieval."""

    name: str
    start_date: str
    end_date: str

    def __post_init__(self):
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
        ):
            raise ValueError(
                "event name must be a nonempty string"
            )

        first = _parse_iso_date(
            self.start_date,
            "event start_date",
        )

        last = _parse_iso_date(
            self.end_date,
            "event end_date",
        )

        if last < first:
            raise ValueError(
                "event end_date must not precede start_date"
            )


def _parse_iso_date(value: str, field_name: str) -> date:
    """Return a strict YYYY-MM-DD calendar date."""
    try:
        if (
            not isinstance(value, str)
            or date.fromisoformat(value).isoformat() != value
        ):
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must use YYYY-MM-DD format"
        ) from exc

    return date.fromisoformat(value)


def resolve_recent_date_range(
    days: int,
    *,
    as_of: str | None = None,
) -> tuple[str, str]:
    """Resolve the most recent N UTC calendar dates to absolute dates.

    The ending date is included. With as_of=None, it is the current UTC
    calendar date. Supplying as_of makes the resolution reproducible.
    """
    if (
        isinstance(days, bool)
        or not isinstance(days, int)
        or days < 1
    ):
        raise ValueError(
            "recent days must be a positive integer"
        )

    if as_of is None:
        last = datetime.now(timezone.utc).date()
    else:
        last = _parse_iso_date(as_of, "as_of")

    first = last - timedelta(days=days - 1)

    return first.isoformat(), last.isoformat()


def _requested_cycles(cycles: Iterable[int]) -> tuple[int, ...]:
    """Materialize and validate an ordered cycle collection."""
    requested = tuple(cycles)

    if not requested:
        raise ValueError("At least one forecast cycle is required")

    if any(
        isinstance(cycle, bool) or not isinstance(cycle, int)
        for cycle in requested
    ):
        raise ValueError("Forecast cycles must be integers")

    if len(set(requested)) != len(requested):
        raise ValueError("Duplicate forecast cycles are not allowed")

    return requested


def _requested_products(products: Iterable[str]) -> tuple[str, ...]:
    """Materialize and validate an ordered product collection."""
    requested = tuple(products)

    if not requested:
        raise ValueError("At least one forecast product is required")

    if any(
        not isinstance(product, str) or not product
        for product in requested
    ):
        raise ValueError("Forecast products must be nonempty strings")

    if len(set(requested)) != len(requested):
        raise ValueError("Duplicate forecast products are not allowed")

    return requested


def plan_operational_configs(
    start_date: str,
    end_date: str,
    *,
    cycles: Iterable[int] = (0,),
    products: Iterable[str] = ("short_range",),
    domain: str = "conus",
) -> list[ForecastConfig]:
    """Expand an inclusive UTC date range into validated forecast configs.

    The planner performs no remote access. Every requested date/cycle/product
    combination must be supported by ForecastConfig; invalid combinations stop
    the complete plan rather than being silently omitted.

    Output order is date, then cycle, then product.
    """
    first = _parse_iso_date(start_date, "start_date")
    last = _parse_iso_date(end_date, "end_date")

    if last < first:
        raise ValueError("end_date must not precede start_date")

    requested_cycles = _requested_cycles(cycles)
    requested_products = _requested_products(products)

    configs: list[ForecastConfig] = []
    current = first

    while current <= last:
        day = current.isoformat()

        for cycle in requested_cycles:
            for product in requested_products:
                try:
                    config = ForecastConfig(
                        date=day,
                        cycle=cycle,
                        product=product,
                        domain=domain,
                    )
                except ValueError as exc:
                    raise ValueError(
                        "Invalid operational configuration "
                        f"for date={day}, cycle={cycle}, "
                        f"product={product!r}, domain={domain!r}: {exc}"
                    ) from exc

                configs.append(config)

        current += timedelta(days=1)

    return configs


def plan_operational_event(
    event: OperationalEvent,
    *,
    cycles: Iterable[int] = (0,),
    products: Iterable[str] = ("short_range",),
    domain: str = "conus",
) -> list[ForecastConfig]:
    """Expand one named event window through the normal request planner.

    Event planning performs no remote access. Spatial selection remains
    independent so the same event can be used with reaches, gages, points,
    bounding boxes, polygons, or a future external event catalogue.
    """
    if not isinstance(event, OperationalEvent):
        raise TypeError(
            "event must be an OperationalEvent"
        )

    return plan_operational_configs(
        event.start_date,
        event.end_date,
        cycles=cycles,
        products=products,
        domain=domain,
    )
