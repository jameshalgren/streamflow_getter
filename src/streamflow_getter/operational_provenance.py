"""Stable row and run-provenance contracts for operational NWM output."""

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
import json
import numbers

import numpy as np

from streamflow_getter.operational_nwm import ForecastConfig
from streamflow_getter.operational_versions import (
    resolve_operational_nwm_version,
)


MANIFEST_SCHEMA_VERSION = 1


OPERATIONAL_SERIES_COLUMNS = (
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


COMBINED_OPERATIONAL_COLUMNS = (
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


COMBINED_ROW_IDENTITY = (
    "forecast_date",
    "forecast_cycle",
    "requested_product",
    "domain",
    "lead_hour",
    "feature_id",
)


def _json_mapping(
    value: Mapping | None,
    *,
    field_name: str,
) -> dict:
    """Copy a mapping and require JSON-compatible provenance values."""
    if value is None:
        result = {}
    elif isinstance(value, Mapping):
        result = dict(value)
    else:
        raise TypeError(
            f"{field_name} must be a mapping"
        )

    try:
        json.dumps(
            result,
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must contain JSON-compatible values"
        ) from exc

    return result


def _created_utc(value: str | None) -> str:
    """Return one explicit timezone-aware UTC run timestamp."""
    if value is None:
        return datetime.now(
            timezone.utc
        ).isoformat()

    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "created_utc must be a timezone-aware ISO timestamp"
        )

    try:
        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError as exc:
        raise ValueError(
            "created_utc must be a timezone-aware ISO timestamp"
        ) from exc

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            "created_utc must be a timezone-aware ISO timestamp"
        )

    return parsed.astimezone(
        timezone.utc
    ).isoformat()


def _materialize_configs(
    configs: Iterable[ForecastConfig],
) -> list[ForecastConfig]:
    """Validate a finite ordered configuration collection."""
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
            "Duplicate forecast configurations are not allowed"
        )

    return requested


def _materialize_reaches(
    reach_ids: Iterable[int],
) -> list[int]:
    """Validate finite positive unique NWM feature IDs."""
    requested = list(reach_ids)

    if not requested:
        raise ValueError(
            "At least one reach is required"
        )

    if any(
        isinstance(reach, (bool, np.bool_))
        or not isinstance(reach, numbers.Integral)
        or int(reach) <= 0
        for reach in requested
    ):
        raise ValueError(
            "Reach IDs must be positive integers"
        )

    requested = [
        int(reach)
        for reach in requested
    ]

    if len(requested) != len(set(requested)):
        raise ValueError(
            "Duplicate reach IDs are not allowed"
        )

    return requested


def expected_combined_row_identities(
    configs: Iterable[ForecastConfig],
    reach_ids: Iterable[int],
    start_hour: int,
    end_hour: int,
    *,
    include_t0: bool = True,
) -> list[tuple]:
    """Return the strict expected row identities for a planned run."""
    if not isinstance(include_t0, bool):
        raise ValueError(
            "include_t0 must be a boolean"
        )

    requested_configs = _materialize_configs(
        configs
    )

    requested_reaches = _materialize_reaches(
        reach_ids
    )

    identities = []

    for config in requested_configs:
        hours = config.forecast_hours(
            start_hour,
            end_hour,
        )

        if include_t0:
            hours.insert(
                0,
                0,
            )

        for hour in hours:
            for reach in requested_reaches:
                identities.append((
                    config.date,
                    config.cycle,
                    config.product,
                    config.domain,
                    hour,
                    reach,
                ))

    if len(identities) != len(set(identities)):
        raise ValueError(
            "Expected combined row identities are not unique"
        )

    return identities


def validate_combined_operational_frame(frame) -> None:
    """Validate the stable successful combined-output row contract."""
    import pandas as pd

    if not isinstance(
        frame,
        pd.DataFrame,
    ):
        raise TypeError(
            "Operational output must be a pandas DataFrame"
        )

    if frame.empty:
        raise ValueError(
            "Operational output must not be empty"
        )

    if tuple(frame.columns) != COMBINED_OPERATIONAL_COLUMNS:
        raise ValueError(
            "Combined operational output columns do not match "
            "the stable contract"
        )

    if frame[list(COMBINED_ROW_IDENTITY)].isnull().any().any():
        raise ValueError(
            "Combined row identity contains null values"
        )

    if frame.duplicated(
        subset=list(COMBINED_ROW_IDENTITY)
    ).any():
        raise ValueError(
            "Duplicate combined operational row identity"
        )

    if not frame["requested_product"].map(
        lambda value:
            isinstance(value, str)
            and bool(value)
    ).all():
        raise ValueError(
            "requested_product must contain nonempty strings"
        )

    if not frame["product"].map(
        lambda value:
            isinstance(value, str)
            and bool(value)
    ).all():
        raise ValueError(
            "product must contain nonempty strings"
        )

    if not frame["domain"].map(
        lambda value:
            isinstance(value, str)
            and bool(value)
    ).all():
        raise ValueError(
            "domain must contain nonempty strings"
        )

    if not frame["method"].map(
        lambda value:
            isinstance(value, str)
            and bool(value)
    ).all():
        raise ValueError(
            "method must contain nonempty strings"
        )

    lead_hours = pd.to_numeric(
        frame["lead_hour"],
        errors="coerce",
    )

    if (
        lead_hours.isna().any()
        or (lead_hours < 0).any()
        or not np.equal(
            lead_hours,
            np.floor(lead_hours),
        ).all()
    ):
        raise ValueError(
            "lead_hour must contain nonnegative integers"
        )

    feature_ids = pd.to_numeric(
        frame["feature_id"],
        errors="coerce",
    )

    if (
        feature_ids.isna().any()
        or (feature_ids <= 0).any()
        or not np.equal(
            feature_ids,
            np.floor(feature_ids),
        ).all()
    ):
        raise ValueError(
            "feature_id must contain positive integers"
        )

    values = pd.to_numeric(
        frame["streamflow_m3s"],
        errors="coerce",
    )

    if (
        values.isna().any()
        or not np.isfinite(values).all()
    ):
        raise ValueError(
            "streamflow_m3s must contain finite numeric values"
        )

    for column in (
        "valid_time",
        "reference_time",
    ):
        parsed = pd.to_datetime(
            frame[column],
            errors="coerce",
            utc=True,
        )

        if parsed.isna().any():
            raise ValueError(
                f"{column} contains invalid timestamps"
            )

    forecast_rows = lead_hours.gt(0)

    if not frame.loc[
        forecast_rows,
        "requested_product",
    ].eq(
        frame.loc[
            forecast_rows,
            "product",
        ]
    ).all():
        raise ValueError(
            "Forecast source product differs from requested product"
        )

    # Analysis t0 intentionally permits product != requested_product.
    # reference_time is source metadata and is never normalized to the
    # forecast cycle here.


def _ordered_counts(values) -> dict[str, int]:
    """Return deterministic string-key counts."""
    counts = Counter(
        str(value)
        for value in values
    )

    return {
        key: int(counts[key])
        for key in sorted(counts)
    }


def build_operational_run_manifest(
    frame,
    configs: Iterable[ForecastConfig],
    reach_ids: Iterable[int],
    start_hour: int,
    end_hour: int,
    *,
    include_t0: bool = True,
    selection: Mapping | None = None,
    cache_policy: Mapping | None = None,
    software: Mapping | None = None,
    diagnostics: Mapping | None = None,
    created_utc: str | None = None,
) -> dict:
    """Build a manifest for one complete strict operational run.

    This version does not describe partial success. Missing or extra row
    identities are rejected rather than represented as a complete run.
    """
    validate_combined_operational_frame(
        frame
    )

    requested_configs = _materialize_configs(
        configs
    )

    requested_reaches = _materialize_reaches(
        reach_ids
    )

    expected = expected_combined_row_identities(
        requested_configs,
        requested_reaches,
        start_hour,
        end_hour,
        include_t0=include_t0,
    )

    actual = [
        tuple(row)
        for row in frame.loc[
            :,
            list(COMBINED_ROW_IDENTITY),
        ].itertuples(
            index=False,
            name=None,
        )
    ]

    expected_set = set(expected)
    actual_set = set(actual)

    missing = expected_set - actual_set
    extra = actual_set - expected_set

    if missing or extra:
        raise ValueError(
            "Combined operational output is incomplete: "
            f"missing={len(missing)}, extra={len(extra)}"
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "created_utc": _created_utc(
            created_utc
        ),
        "status": "complete",
        "selection": _json_mapping(
            selection,
            field_name="selection",
        ),
        "request": {
            "configs": [
                {
                    "forecast_date": config.date,
                    "forecast_cycle": config.cycle,
                    "requested_product": config.product,
                    "domain": config.domain,
                    "nwm_version": resolve_operational_nwm_version(
                        config
                    ),
                }
                for config in requested_configs
            ],
            "reach_ids": requested_reaches,
            "start_hour": start_hour,
            "end_hour": end_hour,
            "include_t0": include_t0,
        },
        "model": {
            "name": "National Water Model",
            "version_basis": "forecast_initialization_utc",
            "operational_versions": sorted({
                version
                for version in (
                    resolve_operational_nwm_version(config)
                    for config in requested_configs
                )
                if version is not None
            }),
            "unresolved_config_count": sum(
                resolve_operational_nwm_version(config) is None
                for config in requested_configs
            ),
        },
        "cache_policy": _json_mapping(
            cache_policy,
            field_name="cache_policy",
        ),
        "software": _json_mapping(
            software,
            field_name="software",
        ),
        "diagnostics": _json_mapping(
            diagnostics,
            field_name="diagnostics",
        ),
        "output_contract": {
            "columns": list(
                COMBINED_OPERATIONAL_COLUMNS
            ),
            "row_identity": list(
                COMBINED_ROW_IDENTITY
            ),
            "requested_product": (
                "forecast product/member requested by the run"
            ),
            "product": (
                "actual NWM source product for the row"
            ),
            "reference_time": (
                "literal source reference-time metadata"
            ),
        },
        "result": {
            "row_count": len(frame),
            "requested_product_counts": _ordered_counts(
                frame["requested_product"]
            ),
            "source_product_counts": _ordered_counts(
                frame["product"]
            ),
            "method_counts": _ordered_counts(
                frame["method"]
            ),
        },
        "completeness": {
            "mode": "strict",
            "expected_row_count": len(expected),
            "actual_row_count": len(actual),
            "missing_row_count": 0,
            "extra_row_count": 0,
            "complete": True,
        },
        "failures": [],
    }

    # Prove the public manifest is JSON serializable.
    json.dumps(
        manifest,
        sort_keys=True,
    )

    return manifest
