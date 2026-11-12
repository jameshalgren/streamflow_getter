"""Execution of planned operational NWM forecast configurations."""

from collections.abc import Iterable

from streamflow_getter import operational_nwm
from streamflow_getter.operational_nwm import ForecastConfig


REQUIRED_SERIES_COLUMNS = (
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


def _materialize_configs(
    configs: Iterable[ForecastConfig],
) -> list[ForecastConfig]:
    """Validate a finite ordered collection of forecast configurations."""
    requested = list(configs)

    if not requested:
        raise ValueError(
            "At least one forecast configuration is required"
        )

    if any(
        not isinstance(config, ForecastConfig)
        for config in requested
    ):
        raise TypeError(
            "configs must contain ForecastConfig instances"
        )

    identities = [
        (
            config.date,
            config.cycle,
            config.product,
            config.domain,
        )
        for config in requested
    ]

    if len(identities) != len(set(identities)):
        raise ValueError(
            "Duplicate operational forecast configurations "
            "are not allowed"
        )

    return requested


def _validate_series_frame(frame, config: ForecastConfig) -> None:
    """Validate the identity contract of one returned series frame."""
    import pandas as pd

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(
            "fetch_operational_series must return a pandas DataFrame"
        )

    missing = [
        column
        for column in REQUIRED_SERIES_COLUMNS
        if column not in frame.columns
    ]

    if missing:
        raise ValueError(
            f"Operational series is missing columns: {missing}"
        )

    if frame.empty:
        raise ValueError(
            "Operational series returned no rows"
        )

    if "requested_product" in frame.columns:
        raise ValueError(
            "Single-configuration series unexpectedly contains "
            "requested_product"
        )

    if not frame["forecast_date"].eq(config.date).all():
        raise ValueError(
            "Operational series returned an unexpected forecast date"
        )

    if not frame["forecast_cycle"].eq(config.cycle).all():
        raise ValueError(
            "Operational series returned an unexpected forecast cycle"
        )

    if not frame["domain"].eq(config.domain).all():
        raise ValueError(
            "Operational series returned an unexpected domain"
        )


def fetch_operational_configs(
    configs: Iterable[ForecastConfig],
    reach_ids: Iterable[int],
    start_hour: int,
    end_hour: int,
    *,
    include_t0: bool = True,
    cache_dir=None,
):
    """Execute validated forecast configurations as one strict request.

    The complete configuration collection and lead windows are validated
    before retrieval. Analysis t0 is decoded once for each unique resolved
    analysis source and then attached to every requested product sharing
    that source.

    The output adds requested_product while preserving product as the
    actual source product. Any retrieval or validation failure propagates;
    partial results are not returned.
    """
    import pandas as pd

    if not isinstance(include_t0, bool):
        raise ValueError(
            "include_t0 must be a boolean"
        )

    requested_configs = _materialize_configs(configs)
    requested_reaches = list(reach_ids)

    if not requested_reaches:
        raise ValueError(
            "At least one reach is required"
        )

    # Validate every product-specific lead window before any retrieval.
    for config in requested_configs:
        config.forecast_hours(
            start_hour,
            end_hour,
        )

    # Cache decoded analysis rows by their actual resolved source identity.
    shared_t0 = {}
    output_frames = []

    for config in requested_configs:
        t0_identity = None
        fetch_t0 = False

        if include_t0:
            t0_source = operational_nwm.resolve_operational_source(
                config,
                0,
            )

            t0_identity = (
                t0_source["reference_path"],
                t0_source["native_url"],
            )

            fetch_t0 = t0_identity not in shared_t0

        frame = operational_nwm.fetch_operational_series(
            config,
            requested_reaches,
            start_hour,
            end_hour,
            include_t0=fetch_t0,
            cache_dir=cache_dir,
        )

        _validate_series_frame(
            frame,
            config,
        )

        is_t0 = frame["lead_hour"].eq(0)

        if include_t0 and fetch_t0:
            t0_frame = frame.loc[is_t0].copy()

            if t0_frame.empty:
                raise ValueError(
                    "Expected analysis t0 rows were not returned"
                )

            if not t0_frame["product"].eq(
                config.spec.analysis_product
            ).all():
                raise ValueError(
                    "Unexpected analysis t0 source product"
                )

            shared_t0[t0_identity] = t0_frame

        elif include_t0:
            if is_t0.any():
                raise ValueError(
                    "Shared analysis t0 was unexpectedly fetched twice"
                )

            t0_frame = shared_t0[t0_identity].copy()

        else:
            if is_t0.any():
                raise ValueError(
                    "Analysis t0 returned when include_t0 is False"
                )

            t0_frame = None

        forecast_frame = frame.loc[~is_t0].copy()

        if forecast_frame.empty:
            raise ValueError(
                "Operational series returned no forecast rows"
            )

        if not forecast_frame["product"].eq(
            config.product
        ).all():
            raise ValueError(
                "Unexpected forecast source product"
            )

        parts = []

        if include_t0:
            parts.append(t0_frame)

        parts.append(forecast_frame)

        current = pd.concat(
            parts,
            ignore_index=True,
        )

        current.insert(
            2,
            "requested_product",
            config.product,
        )

        output_frames.append(current)

    result = pd.concat(
        output_frames,
        ignore_index=True,
    )

    duplicate_key = [
        "forecast_date",
        "forecast_cycle",
        "requested_product",
        "domain",
        "lead_hour",
        "feature_id",
    ]

    if result.duplicated(
        subset=duplicate_key
    ).any():
        raise ValueError(
            "Duplicate combined operational forecast records"
        )

    return result
