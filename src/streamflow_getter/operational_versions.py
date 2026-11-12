"""Operational National Water Model version provenance."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from streamflow_getter.operational_nwm import ForecastConfig


# streamflow_getter's roadmap targets operational workflows from 2018
# onward. NWM v1.1 was the active version at the start of 2018. Exact
# transition timestamps below are based on NWS Service Change Notices.
OPERATIONAL_VERSION_BASELINE_UTC = datetime(
    2018,
    1,
    1,
    0,
    tzinfo=timezone.utc,
)


@dataclass(frozen=True)
class OperationalVersionTransition:
    """One verified NWM operational-version transition."""

    version: str
    effective_utc: datetime
    notice: str


OPERATIONAL_VERSION_TRANSITIONS = (
    OperationalVersionTransition(
        version="1.2",
        effective_utc=datetime(
            2018,
            3,
            6,
            12,
            tzinfo=timezone.utc,
        ),
        notice="NWS SCN18-16",
    ),
    OperationalVersionTransition(
        version="2.0",
        effective_utc=datetime(
            2019,
            6,
            19,
            12,
            tzinfo=timezone.utc,
        ),
        notice="NWS SCN19-42",
    ),
    OperationalVersionTransition(
        version="2.1",
        effective_utc=datetime(
            2021,
            4,
            20,
            12,
            tzinfo=timezone.utc,
        ),
        notice="NWS SCN20-119",
    ),
    OperationalVersionTransition(
        version="3.0",
        effective_utc=datetime(
            2023,
            9,
            20,
            12,
            tzinfo=timezone.utc,
        ),
        notice="NWS SCN23-76",
    ),
    OperationalVersionTransition(
        version="3.1",
        effective_utc=datetime(
            2026,
            8,
            18,
            12,
            tzinfo=timezone.utc,
        ),
        notice="NWS SCN26-64",
    ),
)


def forecast_initialization_utc(
    config: ForecastConfig,
) -> datetime:
    """Return the requested operational initialization as UTC."""
    if not isinstance(
        config,
        ForecastConfig,
    ):
        raise TypeError(
            "config must be a ForecastConfig"
        )

    return datetime.combine(
        date.fromisoformat(
            config.date
        ),
        time(
            hour=config.cycle,
            tzinfo=timezone.utc,
        ),
    )


def resolve_operational_nwm_version(
    config: ForecastConfig,
) -> str | None:
    """Resolve NWM version from the forecast initialization time.

    Version provenance is derived rather than user-selected because
    operational archive paths are date/cycle based and do not encode a
    model-version selector.

    The verified registry covers the streamflow_getter roadmap period
    beginning January 1, 2018. Earlier dates return None rather than
    receiving a guessed version.
    """
    initialization = (
        forecast_initialization_utc(
            config
        )
    )

    if (
        initialization
        < OPERATIONAL_VERSION_BASELINE_UTC
    ):
        return None

    version = "1.1"

    for transition in (
        OPERATIONAL_VERSION_TRANSITIONS
    ):
        if (
            initialization
            >= transition.effective_utc
        ):
            version = (
                transition.version
            )
        else:
            break

    return version
