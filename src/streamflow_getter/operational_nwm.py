"""Configuration and validated extraction for operational NWM forecasts."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import numbers

import numpy as np


@dataclass(frozen=True)
class ProductSpec:
    """Validated source conventions for an operational NWM product."""

    directory: str
    filename_product: str
    channel_family: str
    cycles: tuple[int, ...]
    max_hour: int
    lead_step_hours: int = 1
    analysis_product: str = "analysis_assim"



PRODUCT_SPECS = {
    "short_range": ProductSpec(
        directory="short_range",
        filename_product="short_range",
        channel_family="channel_rt",
        cycles=tuple(range(24)),
        max_hour=18,
    ),
    "medium_range_mem1": ProductSpec(
        directory="medium_range_mem1",
        filename_product="medium_range",
        channel_family="channel_rt_1",
        cycles=(0, 6, 12, 18),
        max_hour=240,
    ),
    "medium_range_mem2": ProductSpec(
        directory="medium_range_mem2",
        filename_product="medium_range",
        channel_family="channel_rt_2",
        cycles=(0, 6, 12, 18),
        max_hour=204,
    ),
    "medium_range_mem3": ProductSpec(
        directory="medium_range_mem3",
        filename_product="medium_range",
        channel_family="channel_rt_3",
        cycles=(0, 6, 12, 18),
        max_hour=204,
    ),
    "medium_range_mem4": ProductSpec(
        directory="medium_range_mem4",
        filename_product="medium_range",
        channel_family="channel_rt_4",
        cycles=(0, 6, 12, 18),
        max_hour=204,
    ),
    "medium_range_mem5": ProductSpec(
        directory="medium_range_mem5",
        filename_product="medium_range",
        channel_family="channel_rt_5",
        cycles=(0, 6, 12, 18),
        max_hour=204,
    ),
    "medium_range_mem6": ProductSpec(
        directory="medium_range_mem6",
        filename_product="medium_range",
        channel_family="channel_rt_6",
        cycles=(0, 6, 12, 18),
        max_hour=204,
    ),
    "medium_range_blend": ProductSpec(
        directory="medium_range_blend",
        filename_product="medium_range_blend",
        channel_family="channel_rt",
        cycles=(0, 6, 12, 18),
        max_hour=240,
        lead_step_hours=1,
    ),

    "medium_range_no_da": ProductSpec(
        directory="medium_range_no_da",
        filename_product="medium_range_no_da",
        channel_family="channel_rt",
        cycles=(0, 6, 12, 18),
        max_hour=240,
        lead_step_hours=3,
        analysis_product="analysis_assim_no_da",
    ),

    "long_range_mem1": ProductSpec(
        directory="long_range_mem1",
        filename_product="long_range",
        channel_family="channel_rt_1",
        cycles=(0, 6, 12, 18),
        max_hour=720,
        lead_step_hours=6,
        analysis_product="analysis_assim",
    ),


    "long_range_mem2": ProductSpec(
        directory="long_range_mem2",
        filename_product="long_range",
        channel_family="channel_rt_2",
        cycles=(0, 6, 12, 18),
        max_hour=720,
        lead_step_hours=6,
        analysis_product="analysis_assim",
    ),
    "long_range_mem3": ProductSpec(
        directory="long_range_mem3",
        filename_product="long_range",
        channel_family="channel_rt_3",
        cycles=(0, 6, 12, 18),
        max_hour=720,
        lead_step_hours=6,
        analysis_product="analysis_assim",
    ),
    "long_range_mem4": ProductSpec(
        directory="long_range_mem4",
        filename_product="long_range",
        channel_family="channel_rt_4",
        cycles=(0, 6, 12, 18),
        max_hour=720,
        lead_step_hours=6,
        analysis_product="analysis_assim",
    ),

}

# Observed CIROH operational medium-range scheduling transition.
MEDIUM_RANGE_HOURLY_START = datetime(2021, 4, 20, 12)

@dataclass(frozen=True)
class ForecastConfig:
    """Identify a supported operational NWM forecast cycle."""

    date: str = "2026-04-19"
    cycle: int = 0
    product: str = "short_range"
    domain: str = "conus"

    def __post_init__(self):
        try:
            if not isinstance(self.date, str) or date.fromisoformat(self.date).isoformat() != self.date:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("date must use YYYY-MM-DD format") from exc

        if isinstance(self.cycle, bool) or not isinstance(self.cycle, int):
            raise ValueError("cycle must be an integer")
        if not 0 <= self.cycle <= 23:
            raise ValueError("cycle must be between 0 and 23")
        if self.product not in PRODUCT_SPECS:
            raise ValueError(
                f"Unsupported operational NWM product: {self.product}"
            )

        if self.domain != "conus":
            raise ValueError("Only the CONUS domain is currently supported")

        if self.cycle not in PRODUCT_SPECS[self.product].cycles:
            raise ValueError(
                f"Unsupported cycle {self.cycle} for {self.product}"
            )

    @property
    def spec(self) -> ProductSpec:
        return PRODUCT_SPECS[self.product]

    @property
    def lead_step_hours(self) -> int:
        """Return the forecast lead interval for this product and cycle."""
        if self.product in {
            f"medium_range_mem{i}" for i in range(1, 7)
        }:
            initialization = datetime.combine(
                date.fromisoformat(self.date),
                datetime.min.time(),
            ).replace(hour=self.cycle)

            if initialization < MEDIUM_RANGE_HOURLY_START:
                return 3

        return self.spec.lead_step_hours

    @property
    def date_folder(self) -> str:
        return "nwm." + self.date.replace("-", "")

    @property
    def cycle_name(self) -> str:
        return f"t{self.cycle:02d}z"


    def forecast_hours(self, start_hour: int, end_hour: int) -> list[int]:
        """Select available forecast leads within an inclusive hour window."""
        if (
            isinstance(start_hour, bool)
            or not isinstance(start_hour, int)
            or isinstance(end_hour, bool)
            or not isinstance(end_hour, int)
        ):
            raise ValueError("Forecast hours must be integers")

        if start_hour < 1 or end_hour < start_hour:
            raise ValueError("Invalid forecast hour range")

        if end_hour > self.spec.max_hour:
            raise ValueError(
                f"Forecast hour must not exceed {self.spec.max_hour} "
                f"for {self.product}"
            )

        step = self.lead_step_hours
        if isinstance(step, bool) or not isinstance(step, int) or step < 1:
            raise ValueError("Forecast lead step must be a positive integer")
        first = ((start_hour + step - 1) // step) * step

        if first > end_hour:
            raise ValueError(
                "No available forecast leads in the requested hour range"
            )

        return list(range(first, end_hour + 1, step))


    def filename(self, hour: int) -> str:
        """Build a validated operational channel forecast filename."""
        if isinstance(hour, bool) or not isinstance(hour, int):
            raise ValueError("Forecast lead hour must be an integer")

        if not 1 <= hour <= self.spec.max_hour:
            raise ValueError(
                f"Forecast hour must be between 1 and "
                f"{self.spec.max_hour} for {self.product}"
            )

        step = self.lead_step_hours

        if isinstance(step, bool) or not isinstance(step, int) or step < 1:
            raise ValueError("Forecast lead step must be a positive integer")

        if hour % step != 0:
            raise ValueError(
                f"Forecast hour must be a multiple of "
                f"{step} for {self.product}"
            )

        return (
            f"nwm.{self.cycle_name}.{self.spec.filename_product}."
            f"{self.spec.channel_family}.f{hour:03d}.{self.domain}.nc"
        )



    def native_url(self, hour: int) -> str:
        return (
            "https://storage.googleapis.com/national-water-model/"
            f"{self.date_folder}/{self.spec.directory}/{self.filename(hour)}"
        )

    def reference_path(self, hour: int) -> str:
        return (
            "ciroh-nwm-zarr-copy/national-water-model/"
            f"{self.date_folder}/{self.spec.directory}/{self.filename(hour)}.json"
        )



    def analysis_filename(self) -> str:
        """Build the configured CONUS analysis t0 filename."""
        return (
            f"nwm.{self.cycle_name}.{self.spec.analysis_product}."
            f"channel_rt.tm00.{self.domain}.nc"
        )

    def analysis_native_url(self) -> str:
        """Return the configured native analysis t0 URL."""
        return (
            "https://storage.googleapis.com/national-water-model/"
            f"{self.date_folder}/{self.spec.analysis_product}/"
            f"{self.analysis_filename()}"
        )

    def analysis_reference_path(self) -> str:
        """Return the configured CIROH analysis t0 reference."""
        return (
            "ciroh-nwm-zarr-copy/national-water-model/"
            f"{self.date_folder}/{self.spec.analysis_product}/"
            f"{self.analysis_filename()}.json"
        )


    def validate_analysis_timestamps(
        self,
        valid_time,
        reference_time,
    ) -> None:
        """Validate analysis t0 without assuming a reference-time offset."""
        expected_valid = np.datetime64(
            datetime.combine(
                date.fromisoformat(self.date),
                datetime.min.time(),
            ).replace(hour=self.cycle),
            "s",
        )

        actual_valid = np.datetime64(valid_time, "s")
        actual_reference = np.datetime64(reference_time, "s")

        if np.isnat(actual_valid) or actual_valid != expected_valid:
            raise ValueError("Incorrect analysis t0 valid time")

        if np.isnat(actual_reference):
            raise ValueError("Invalid analysis t0 reference time")


    def validate_timestamps(self, hour: int, valid_time, reference_time) -> None:
        """Verify forecast timestamps against the requested cycle."""
        self.filename(hour)
        expected_reference = datetime.combine(
            date.fromisoformat(self.date), datetime.min.time()
        ).replace(hour=self.cycle)
        expected_valid = expected_reference + timedelta(hours=hour)
        actual_reference = np.datetime64(reference_time, "s")
        actual_valid = np.datetime64(valid_time, "s")
        if actual_reference != np.datetime64(expected_reference, "s"):
            raise ValueError(f"Incorrect forecast reference time for f{hour:03d}")
        if actual_valid != np.datetime64(expected_valid, "s"):
            raise ValueError(f"Incorrect forecast valid time for f{hour:03d}")


def resolve_operational_source(
    config: ForecastConfig,
    hour: int,
) -> dict:
    """Resolve a supported NWM forecast or analysis t0 source."""
    if isinstance(hour, bool) or not isinstance(hour, int):
        raise ValueError("Lead hour must be an integer")

    if hour < 0:
        raise ValueError("Lead hour must be nonnegative")

    if hour == 0:
        return {
            "source_product": config.spec.analysis_product,
            "filename": config.analysis_filename(),
            "native_url": config.analysis_native_url(),
            "reference_path": config.analysis_reference_path(),
            "lead_hour": 0,
        }

    return {
        "source_product": config.product,
        "filename": config.filename(hour),
        "native_url": config.native_url(hour),
        "reference_path": config.reference_path(hour),
        "lead_hour": hour,
    }

def extract_streamflow(ds, reach_ids: list[int]) -> dict[int, float]:
    """Extract one-timestep streamflow by exact NWM feature ID.

    Preserve requested order and reject missing or duplicated requested IDs,
    duplicated matching dataset IDs, malformed IDs, and nonfinite values.
    """
    requested = list(reach_ids)

    if not requested:
        raise ValueError("At least one reach is required")

    if any(
        isinstance(reach, (bool, np.bool_))
        or not isinstance(reach, numbers.Integral)
        or int(reach) <= 0
        for reach in requested
    ):
        raise ValueError("Reach IDs must be positive integers")

    requested = [int(reach) for reach in requested]

    if len(requested) != len(set(requested)):
        raise ValueError("Duplicate reach IDs are not allowed")

    if "feature_id" not in ds or "streamflow" not in ds:
        raise ValueError("NWM dataset requires feature_id and streamflow")
    ids = np.asarray(ds["feature_id"].values)
    if ids.ndim != 1:
        raise ValueError("feature_id must be one-dimensional")

    mapping = {}
    wanted = set(requested)
    for position, raw_id in enumerate(ids):
        if isinstance(raw_id, (bool, np.bool_)) or not isinstance(
            raw_id, numbers.Integral
        ):
            raise ValueError("NWM feature IDs must be integers")
        feature_id = int(raw_id)
        if feature_id in wanted:
            if feature_id in mapping:
                raise ValueError(f"Duplicate feature ID {feature_id}")
            mapping[feature_id] = position

    missing = wanted - mapping.keys()
    if missing:
        raise ValueError(f"Missing reaches: {sorted(missing)}")
    indices = [mapping[reach] for reach in requested]
    selected_ids = np.asarray(ds["feature_id"].isel(feature_id=indices).values)
    if not np.array_equal(selected_ids, np.asarray(requested)):
        raise ValueError("Feature-ID mismatch during streamflow extraction")

    flows = np.asarray(ds["streamflow"].isel(feature_id=indices).values, dtype=float)
    if flows.shape != (len(requested),):
        raise ValueError("Unexpected streamflow shape")
    if not np.isfinite(flows).all():
        raise ValueError("Non-finite streamflow values found")
    return {reach: float(flow) for reach, flow in zip(requested, flows)}

def prepare_operational_reference(
    config: ForecastConfig,
    hour: int,
    *,
    cache_dir=None,
) -> dict:
    """Prepare one validated Kerchunk reference without opening model arrays.

    With a cache directory, store or reuse the existing validated record,
    including remote freshness checks. Otherwise, return it without caching.
    Return source identity, reference contents, and reference-size accounting.
    Missing remote references are classified with their original cause;
    other acquisition, local I/O, and integrity errors propagate unchanged.
    """
    import json
    from pathlib import Path

    import s3fs

    from streamflow_getter.reference_cache import (
        RemoteReferenceNotFoundError,
        fetch_remote_metadata,
        load_fresh_reference,
    )
    from streamflow_getter.reference_validation import (
        validate_reference,
        valid_source_identity,
    )

    source = resolve_operational_source(config, hour)
    reference_path = source["reference_path"]
    expected_url = source["native_url"]
    s3 = s3fs.S3FileSystem(anon=True)

    def downloader():
        try:
            with s3.open(reference_path, "rb") as file:
                return file.read()
        except FileNotFoundError as exc:
            raise RemoteReferenceNotFoundError(
                f"Kerchunk reference body not found: {reference_path}"
            ) from exc

    if cache_dir is None:
        reference_bytes = downloader()
        reference = json.loads(reference_bytes)
        reference_json_bytes = len(reference_bytes)
    else:
        cache_root = Path(cache_dir).expanduser()
        cache_file = (
            cache_root
            / config.date_folder
            / source["source_product"]
            / f'{source["filename"]}.cache.json'
        )

        def metadata_provider():
            return fetch_remote_metadata(
                reference_path,
                expected_url,
                s3=s3,
            )

        reference = load_fresh_reference(
            cache_file,
            expected_url,
            metadata_provider,
            downloader,
        )
        # Serialized reference size, not bytes transferred over the network.
        reference_json_bytes = len(json.dumps(reference).encode("utf-8"))

    if not validate_reference(reference):
        raise ValueError("Invalid Kerchunk reference structure")
    if not valid_source_identity(reference, expected_url):
        raise ValueError("Incorrect Kerchunk source identity")

    return {
        "source": source,
        "reference": reference,
        "reference_json_bytes": reference_json_bytes,
    }


def prepare_operational_references(
    configs: Iterable[ForecastConfig],
    start_hour: int,
    end_hour: int,
    *,
    cache_dir,
    include_t0: bool = True,
) -> list[dict]:
    """Prepare unique references for a finite collection of forecast cycles.

    Validate the complete request before acquisition. Reuse each product's
    lead schedule and include analysis t0 by default. References sharing the
    same reference path and native URL are prepared once, in first-seen order.
    Return compact summaries; full references remain in the explicit cache.
    Acquisition errors propagate, leaving earlier validated records reusable.
    """
    from pathlib import Path

    if cache_dir is None or (
        isinstance(cache_dir, str) and not cache_dir.strip()
    ):
        raise ValueError("cache_dir is required for batch reference preparation")
    cache_root = Path(cache_dir).expanduser()

    if not isinstance(include_t0, bool):
        raise ValueError("include_t0 must be a boolean")

    requested = list(configs)
    if not requested:
        raise ValueError("At least one forecast configuration is required")

    planned = {}
    for config in requested:
        if not isinstance(config, ForecastConfig):
            raise TypeError("configs must contain ForecastConfig instances")
        hours = config.forecast_hours(start_hour, end_hour)
        if include_t0:
            hours.insert(0, 0)
        for hour in hours:
            source = resolve_operational_source(config, hour)
            identity = (source["reference_path"], source["native_url"])
            planned.setdefault(identity, (config, hour))

    summaries = []
    for config, hour in planned.values():
        prepared = prepare_operational_reference(config, hour, cache_dir=cache_root)
        summaries.append({
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "domain": config.domain,
            "source": prepared["source"],
            "reference_json_bytes": prepared["reference_json_bytes"],
        })
    return summaries


def read_kerchunk_forecast(
    config: ForecastConfig,
    hour: int,
    reach_ids: list[int],
    *,
    cache_dir=None,
) -> dict:
    """Read an operational forecast or analysis t0 using Kerchunk.

    Cache use is opt-in; cached references undergo the same validation.
    """
    import fsspec
    import xarray as xr

    prepared = prepare_operational_reference(config, hour, cache_dir=cache_dir)
    source = prepared["source"]
    reference = prepared["reference"]
    reference_json_bytes = prepared["reference_json_bytes"]

    fs = fsspec.filesystem(
        "reference",
        fo=reference,
        remote_protocol="https",
        remote_options={"asynchronous": True},
        asynchronous=True,
        skip_instance_cache=True,
    )

    with xr.open_zarr(
        fs.get_mapper(""),
        consolidated=False,
        zarr_format=2,
        mask_and_scale={"feature_id": False},
    ) as ds:
        flows = extract_streamflow(ds, reach_ids)
        valid_time = ds.time.values[0]
        reference_time = ds.reference_time.values[0]

        if hour == 0:
            config.validate_analysis_timestamps(valid_time, reference_time)
        else:
            config.validate_timestamps(hour, valid_time, reference_time)

    return {
        "forecast_date": config.date,
        "forecast_cycle": config.cycle,
        "product": source["source_product"],
        "domain": config.domain,
        "lead_hour": hour,
        "method": "kerchunk",
        "valid_time": str(valid_time),
        "reference_time": str(reference_time),
        "streamflow_m3s": flows,
        "reference_json_bytes": reference_json_bytes,
    }


def read_native_forecast(
    config: ForecastConfig,
    hour: int,
    reach_ids: list[int],
) -> dict:
    """Read an operational forecast or analysis t0 from native NetCDF."""
    import fsspec
    import xarray as xr

    source = resolve_operational_source(config, hour)
    url = source["native_url"]

    with fsspec.open(
        url,
        mode="rb",
        block_size=1024 * 1024,
        cache_type="bytes",
    ) as remote_file:
        with xr.open_dataset(remote_file, engine="h5netcdf") as ds:
            flows = extract_streamflow(ds, reach_ids)
            valid_time = ds.time.values[0]
            reference_time = ds.reference_time.values[0]

            if hour == 0:
                config.validate_analysis_timestamps(valid_time, reference_time)
            else:
                config.validate_timestamps(hour, valid_time, reference_time)

    return {
        "forecast_date": config.date,
        "forecast_cycle": config.cycle,
        "product": source["source_product"],
        "domain": config.domain,
        "lead_hour": hour,
        "method": "native_remote",
        "valid_time": str(valid_time),
        "reference_time": str(reference_time),
        "streamflow_m3s": flows,
        "reference_json_bytes": 0,
    }


def fetch_operational_forecast(
    config: ForecastConfig,
    hour: int,
    reach_ids: list[int],
    *,
    cache_dir=None,
) -> dict:
    """Use Kerchunk first, with controlled native fallback.

    With caching, only a classified missing remote reference permits fallback.
    Other cached errors propagate; uncached access handling is unchanged.
    """
    import json

    from streamflow_getter.reference_cache import RemoteReferenceNotFoundError

    try:
        if cache_dir is None:
            return read_kerchunk_forecast(config, hour, reach_ids)
        return read_kerchunk_forecast(
            config,
            hour,
            reach_ids,
            cache_dir=cache_dir,
        )
    except PermissionError:
        raise
    except RemoteReferenceNotFoundError as exc:
        kerchunk_error = exc
    except (OSError, json.JSONDecodeError) as exc:
        if cache_dir is not None:
            raise
        kerchunk_error = exc

    try:
        result = read_native_forecast(config, hour, reach_ids)
    except Exception as native_error:
        failure = RuntimeError(
            "Both Kerchunk and native NWM retrieval failed"
        )
        failure.add_note(
            f"Kerchunk fallback reason: "
            f"{type(kerchunk_error).__name__}: {kerchunk_error}"
        )
        raise failure from native_error

    result["fallback_reason"] = (
        f"{type(kerchunk_error).__name__}: {kerchunk_error}"
    )
    return result



def fetch_operational_series(
    config: ForecastConfig,
    reach_ids: list[int],
    start_hour: int,
    end_hour: int,
    *,
    include_t0: bool = True,
    cache_dir=None,
):
    """Retrieve a validated operational NWM streamflow time series.

    Analysis t0 is included by default. Each row retains the original
    source reference time, forecast cycle, lead hour, and product.
    """
    import pandas as pd


    if (
        isinstance(start_hour, bool)
        or not isinstance(start_hour, int)
        or isinstance(end_hour, bool)
        or not isinstance(end_hour, int)
    ):
        raise ValueError("Forecast hours must be integers")

    if start_hour < 1 or end_hour < start_hour:
        raise ValueError("Invalid forecast hour range")


    # Select only available forecast leads before remote access.
    hours = config.forecast_hours(start_hour, end_hour)


    if not isinstance(include_t0, bool):
        raise ValueError("include_t0 must be a boolean")

    requested = list(reach_ids)

    if not requested:
        raise ValueError("At least one reach is required")

    if any(
        isinstance(reach, (bool, np.bool_))
        or not isinstance(reach, numbers.Integral)
        or int(reach) <= 0
        for reach in requested
    ):
        raise ValueError("Reach IDs must be positive integers")

    requested = [int(reach) for reach in requested]

    if len(requested) != len(set(requested)):
        raise ValueError("Duplicate reach IDs are not allowed")

    if include_t0:
        hours.insert(0, 0)

    records = []

    for hour in hours:
        if cache_dir is None:
            result = fetch_operational_forecast(
                config,
                hour,
                requested,
            )
        else:
            result = fetch_operational_forecast(
                config,
                hour,
                requested,
                cache_dir=cache_dir,
            )

        if result["lead_hour"] != hour:
            raise ValueError("Unexpected forecast lead hour")

        if result["forecast_date"] != config.date:
            raise ValueError("Unexpected forecast date")

        if result["forecast_cycle"] != config.cycle:
            raise ValueError("Unexpected forecast cycle")

        if result["domain"] != config.domain:
            raise ValueError("Unexpected NWM domain")

        if hour == 0:
            config.validate_analysis_timestamps(
                result["valid_time"],
                result["reference_time"],
            )
        else:
            config.validate_timestamps(
                hour,
                result["valid_time"],
                result["reference_time"],
            )

        expected_product = (
            config.spec.analysis_product if hour == 0 else config.product
        )

        if result["product"] != expected_product:
            raise ValueError("Unexpected NWM source product")

        if set(result["streamflow_m3s"]) != set(requested):
            raise ValueError("Unexpected feature IDs in forecast result")


        if not np.isfinite(
            list(result["streamflow_m3s"].values())
        ).all():
            raise ValueError("Non-finite streamflow values found")


        for reach in requested:
            records.append({
                "forecast_date": result["forecast_date"],
                "forecast_cycle": result["forecast_cycle"],
                "product": result["product"],
                "domain": result["domain"],
                "lead_hour": result["lead_hour"],
                "feature_id": reach,
                "valid_time": result["valid_time"],
                "reference_time": result["reference_time"],
                "streamflow_m3s": result["streamflow_m3s"][reach],
                "method": result["method"],
            })

    frame = pd.DataFrame.from_records(records)

    if frame.duplicated(
        subset=["forecast_date", "forecast_cycle",
                "lead_hour", "feature_id"]
    ).any():
        raise ValueError("Duplicate forecast records")

    return frame
