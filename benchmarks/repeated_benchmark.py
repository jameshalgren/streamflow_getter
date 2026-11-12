"""Repeatable benchmark for NWM operational forecast retrieval."""

import argparse
import csv
import json
import random
import statistics
import time
import urllib.request
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import fsspec
import numpy as np
import s3fs
import xarray as xr
import tempfile

from http_trace import trace_http_reads, trace_native_http_reads
from dataclasses import dataclass


DATA_DIR = Path("benchmarks/data")
RESULTS_DIR = Path("benchmarks/results")



@dataclass(frozen=True)
class ForecastConfig:
    """Identify one operational NWM forecast cycle."""

    date: str = "2026-04-19"
    cycle: int = 0
    product: str = "short_range"
    domain: str = "conus"

    def validate_timestamps(self, hour, valid_time, reference_time):
        """Verify timestamps against the requested forecast cycle."""
        expected_reference = datetime.strptime(
            self.date, "%Y-%m-%d"
        ).replace(hour=self.cycle)

        expected_valid = expected_reference + timedelta(hours=hour)

        actual_reference = np.datetime64(reference_time, "s")
        actual_valid = np.datetime64(valid_time, "s")

        if actual_reference != np.datetime64(expected_reference, "s"):
            raise ValueError(
                f"Incorrect forecast reference time for f{hour:03d}"
            )

        if actual_valid != np.datetime64(expected_valid, "s"):
            raise ValueError(
                f"Incorrect forecast valid time for f{hour:03d}"
            )



    @property
    def date_folder(self):
        return "nwm." + self.date.replace("-", "")

    @property
    def cycle_name(self):
        return f"t{self.cycle:02d}z"

    def filename(self, hour):
        return (
            f"nwm.{self.cycle_name}.{self.product}."
            f"channel_rt.f{hour:03d}.{self.domain}.nc"
        )

    def local_path(self, hour):
        return (
            DATA_DIR
            / self.date_folder
            / self.product
            / self.filename(hour)
        )

    def native_url(self, hour):
        return (
            "https://storage.googleapis.com/national-water-model/"
            f"{self.date_folder}/{self.product}/"
            f"{self.filename(hour)}"
        )

    def reference_path(self, hour):
        return (
            "ciroh-nwm-zarr-copy/national-water-model/"
            f"{self.date_folder}/{self.product}/"
            f"{self.filename(hour)}.json"
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Benchmark NWM Kerchunk and native NetCDF retrieval."
    )
    parser.add_argument("--start-hour", type=int, default=1)
    parser.add_argument("--end-hour", type=int, default=6)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument(
        "--date",
        type=str,
        default="2026-04-19",
        help="NWM forecast date in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--cycle",
        type=int,
        default=0,
        help="Forecast initialization cycle (0–23 UTC).",
    )


    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="First forecast date for multi-day benchmarking.",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Last forecast date for multi-day benchmarking.",
    )



    parser.add_argument(
        "--output-prefix",
        type=str,
        default="repeated_benchmark",
        help="Prefix for benchmark CSV output filenames.",
    )

    parser.add_argument(
        "--reach",
        type=int,
        default=None,
        help="Single NWM feature ID (legacy option).",
    )

    parser.add_argument(
        "--reaches",
        type=int,
        nargs="+",
        default=None,
        help="One or more NWM feature IDs.",
    )
    args = parser.parse_args()

    try:
        if args.start_date is not None or args.end_date is not None:
            if args.start_date is None or args.end_date is None:
                parser.error(
                    "--start-date and --end-date must be provided together."
                )

            start = datetime.strptime(args.start_date, "%Y-%m-%d")
            end = datetime.strptime(args.end_date, "%Y-%m-%d")

            if (
                start.strftime("%Y-%m-%d") != args.start_date
                or end.strftime("%Y-%m-%d") != args.end_date
            ):
                raise ValueError

            if start > end:
                parser.error("--start-date must not exceed --end-date.")

            args.dates = [
                (start + timedelta(days=i)).strftime("%Y-%m-%d")
                for i in range((end - start).days + 1)
            ]

        else:
            parsed = datetime.strptime(args.date, "%Y-%m-%d")

            if parsed.strftime("%Y-%m-%d") != args.date:
                raise ValueError

            args.dates = [args.date]

    except ValueError:
        parser.error("Forecast dates must use valid YYYY-MM-DD values.")


    if not 0 <= args.cycle <= 23:
        parser.error("--cycle must be between 0 and 23.")

    if not 1 <= args.start_hour <= args.end_hour <= 18:
        parser.error("Forecast hours must be between 1 and 18.")
    if args.trials < 1:
        parser.error("--trials must be at least 1.")
    if args.reach is not None and args.reaches is not None:
        parser.error("Use either --reach or --reaches, not both.")

    if args.reaches is not None:
        args.reach_ids = args.reaches
    elif args.reach is not None:
        args.reach_ids = [args.reach]
    else:
        args.reach_ids = [3586192]

    if len(set(args.reach_ids)) != len(args.reach_ids):
        parser.error("Duplicate reach IDs are not allowed.")
    return args



def download_native(hour, config=None):
    """Download a native NWM file using atomic replacement."""
    if config is None:
        config = ForecastConfig()

    path = config.local_path(hour)
    url = config.native_url(hour)

    path.parent.mkdir(parents=True, exist_ok=True)

    bytes_received = 0
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".nwm-download-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)

            with urllib.request.urlopen(
                url, timeout=60
            ) as response:
                expected_size = response.headers.get(
                    "Content-Length"
                )

                while True:
                    chunk = response.read(1024 * 1024)

                    if not chunk:
                        break

                    temporary.write(chunk)
                    bytes_received += len(chunk)

        if expected_size is not None:
            if bytes_received != int(expected_size):
                raise IOError(
                    "Incomplete NWM download: "
                    f"expected {expected_size} bytes, "
                    f"received {bytes_received}"
                )

        os.replace(temporary_path, path)

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return path, bytes_received


def open_kerchunk(hour, config=None):
    """Open Kerchunk references for the selected NWM forecast."""
    if config is None:
        config = ForecastConfig()

    s3 = s3fs.S3FileSystem(anon=True)

    with s3.open(config.reference_path(hour), "rb") as f:
        reference_bytes = f.read()

    reference = json.loads(reference_bytes)

    fs = fsspec.filesystem(
        "reference",
        fo=reference,
        remote_protocol="https",
        remote_options={"asynchronous": True},
        asynchronous=True,
        skip_instance_cache=True,
    )

    ds = xr.open_zarr(
        fs.get_mapper(""),
        consolidated=False,
        zarr_format=2,
    )

    return ds, len(reference_bytes)


def verify_reach(hour, reaches, config=None):
    """Resolve NWM feature IDs for the selected forecast."""
    if config is None:
        config = ForecastConfig()

    path = config.local_path(hour)

    if not path.exists():
        download_native(hour, config)

    if isinstance(reaches, (int, np.integer)):
        reaches = [int(reaches)]

    reaches = list(reaches)

    if not reaches:
        raise ValueError("At least one reach is required")

    if len(set(reaches)) != len(reaches):
        raise ValueError("Duplicate reach IDs are not allowed")

    with xr.open_dataset(path, engine="h5netcdf") as ds:
        ids = ds.feature_id.values

        # Build a lookup only for requested reaches.
        requested = set(reaches)
        mapping = {}

        for index, feature_id in enumerate(ids):
            feature_id = int(feature_id)

            if feature_id in requested:
                if feature_id in mapping:
                    raise ValueError(
                        f"Duplicate feature ID {feature_id}"
                    )

                mapping[feature_id] = index

        missing = requested - mapping.keys()

        if missing:
            raise ValueError(
                f"Missing reaches in f{hour:03d}: {sorted(missing)}"
            )

    return [mapping[reach] for reach in reaches]


def extract_batch(ds, indices, expected_reaches):
    """Extract streamflow for verified NWM reach indices."""
    selected_ids = np.asarray(
        ds.feature_id.isel(feature_id=indices).values
    )

    expected_ids = np.asarray(expected_reaches)

    if not np.array_equal(selected_ids, expected_ids):
        raise ValueError(
            "Feature-ID mismatch during batch extraction"
        )

    flows = np.asarray(
        ds.streamflow.isel(feature_id=indices).values,
        dtype=float,
    )

    if flows.shape != expected_ids.shape:
        raise ValueError("Unexpected batch streamflow shape")

    if not np.isfinite(flows).all():
        raise ValueError("Non-finite streamflow values found")

    return flows



def read_native(hour, indices, reaches, config=None):
    """Read multiple reaches from the selected local NWM forecast."""
    if config is None:
        config = ForecastConfig()

    path = config.local_path(hour)

    with xr.open_dataset(path, engine="h5netcdf") as ds:
        flows = extract_batch(ds, indices, reaches)

        valid_time = str(ds.time.values[0])
        reference_time = str(ds.reference_time.values[0])

    return flows, valid_time, reference_time

def read_native_remote(hour, indices, reaches, config=None):
    """Read multiple reaches from the selected remote NWM forecast."""
    if config is None:
        config = ForecastConfig()

    url = config.native_url(hour)

    with trace_native_http_reads() as calls:
        with fsspec.open(
            url,
            mode="rb",
            block_size=1024 * 1024,
            cache_type="bytes",
        ) as remote_file:
            with xr.open_dataset(
                remote_file,
                engine="h5netcdf",
            ) as ds:
                flows = extract_batch(ds, indices, reaches)
                valid_time = str(ds.time.values[0])
                reference_time = str(ds.reference_time.values[0])

    response_bytes = sum(
        call["bytes_returned"] for call in calls
    )

    return (
        flows,
        valid_time,
        reference_time,
        len(calls),
        response_bytes,
    )



def read_kerchunk(hour, indices, reaches, config=None):
    """Read multiple reaches from the selected Kerchunk forecast."""
    if config is None:
        config = ForecastConfig()

    with trace_http_reads() as calls:
        ds, reference_bytes = open_kerchunk(hour, config)

        try:
            flows = extract_batch(ds, indices, reaches)
            valid_time = str(ds.time.values[0])
            reference_time = str(ds.reference_time.values[0])
        finally:
            ds.close()

    chunk_bytes = sum(
        call["bytes_returned"] for call in calls
    )

    return (
        flows,
        valid_time,
        reference_time,
        len(calls),
        chunk_bytes,
        reference_bytes,
    )





def run_forecast(config, args, rng):
    """Benchmark one forecast date and return validated records."""
    hours = list(range(args.start_hour, args.end_hour + 1))
    reaches = args.reach_ids
    indices = {}

    print(
        f"\nForecast: {config.date} "
        f"{config.cycle_name} {config.product}"
    )
    print("Verifying reach identity before timed trials...")

    for hour in hours:
        indices[hour] = verify_reach(hour, reaches, config)
        print(f"f{hour:03d}: {len(reaches)} reaches verified")

    operation_records = []
    flow_records = []

    for trial in range(1, args.trials + 1):
        for hour in hours:
            methods = [
                "kerchunk",
                "native_remote",
                "native_download",
                "native_local",
            ]
            rng.shuffle(methods)

            print(f"\nTrial {trial}, f{hour:03d}: {methods}")

            for method in methods:
                start = time.perf_counter()

                if method == "kerchunk":
                    (
                        flows,
                        valid_time,
                        reference_time,
                        requests,
                        chunk_bytes,
                        reference_bytes,
                    ) = read_kerchunk(
                        hour, indices[hour], reaches, config
                    )
                    response_bytes = chunk_bytes + reference_bytes

                elif method == "native_download":
                    _, response_bytes = download_native(hour, config)
                    flows, valid_time, reference_time = read_native(
                        hour, indices[hour], reaches, config
                    )
                    requests = 1
                    reference_bytes = 0

                elif method == "native_remote":
                    (
                        flows,
                        valid_time,
                        reference_time,
                        requests,
                        response_bytes,
                    ) = read_native_remote(
                        hour, indices[hour], reaches, config
                    )
                    reference_bytes = 0

                else:
                    flows, valid_time, reference_time = read_native(
                        hour, indices[hour], reaches, config
                    )
                    requests = 0
                    response_bytes = 0
                    reference_bytes = 0

                elapsed = time.perf_counter() - start

                if len(flows) != len(reaches):
                    raise ValueError(
                        f"Unexpected flow count for {method}"
                    )

                config.validate_timestamps(
                    hour, valid_time, reference_time
                )

                operation_records.append({
                    "forecast_date": config.date,
                    "forecast_cycle": config.cycle,
                    "product": config.product,
                    "domain": config.domain,
                    "trial": trial,
                    "hour": hour,
                    "method": method,
                    "reach_count": len(reaches),
                    "elapsed_seconds": elapsed,
                    "http_read_count": requests,
                    "response_body_bytes": response_bytes,
                    "reference_json_bytes": reference_bytes,
                })

                for reach, flow in zip(reaches, flows):
                    flow_records.append({
                        "forecast_date": config.date,
                        "forecast_cycle": config.cycle,
                        "product": config.product,
                        "domain": config.domain,
                        "trial": trial,
                        "hour": hour,
                        "method": method,
                        "reach_id": reach,
                        "valid_time": valid_time,
                        "reference_time": reference_time,
                        "streamflow_m3s": float(flow),
                    })

                print(
                    f"  {method:18} "
                    f"{elapsed:.3f}s reaches={len(reaches)}"
                )

    # Validate scientific agreement within this forecast only.
    for hour in hours:
        for reach in reaches:
            matching = [
                r for r in flow_records
                if r["hour"] == hour
                and r["reach_id"] == reach
            ]

            values = np.array([
                r["streamflow_m3s"] for r in matching
            ])

            if not np.allclose(
                values, values[0],
                rtol=1e-6,
                atol=1e-6,
                equal_nan=True,
            ):
                raise ValueError(
                    f"Streamflow mismatch: "
                    f"{config.date}, f{hour:03d}, reach {reach}"
                )

            if len({r["valid_time"] for r in matching}) != 1:
                raise ValueError(
                    f"Valid-time mismatch: {config.date}, f{hour:03d}"
                )

            if len({r["reference_time"] for r in matching}) != 1:
                raise ValueError(
                    f"Reference-time mismatch: {config.date}, f{hour:03d}"
                )

    return operation_records, flow_records


def main(args=None):
    """Run one or more forecast dates and save consolidated results."""
    if args is None:
        args = parse_args()

    dates = getattr(args, "dates", None)
    if dates is None:
        dates = [getattr(args, "date", "2026-04-19")]

    if not 1 <= len(dates) <= 7:
        raise ValueError(
            "Multi-day benchmark is limited to 7 dates per execution"
        )

    if len(set(dates)) != len(dates):
        raise ValueError("Duplicate forecast dates are not allowed")

    operation_output = RESULTS_DIR / f"{args.output_prefix}.csv"
    flow_output = RESULTS_DIR / f"{args.output_prefix}_flows.csv"

    if operation_output.exists() or flow_output.exists():
        raise FileExistsError(
            "Benchmark output already exists. "
            "Choose a different --output-prefix."
        )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    operation_records = []
    flow_records = []
    rng = random.Random(42)

    for date in dates:
        config = ForecastConfig(
            date=date,
            cycle=getattr(args, "cycle", 0),
        )

        operations, flows = run_forecast(config, args, rng)
        operation_records.extend(operations)
        flow_records.extend(flows)

    # Write results only after every forecast passes validation.

    # Write both CSV files before publishing either result.
    temporary_paths = []
    published_paths = []

    try:
        for destination, records in (
            (operation_output, operation_records),
            (flow_output, flow_records),
        ):
            with tempfile.NamedTemporaryFile(
                mode="w",
                newline="",
                encoding="utf-8",
                dir=RESULTS_DIR,
                prefix=".benchmark-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary_paths.append(temporary_path)

                writer = csv.DictWriter(
                    temporary,
                    fieldnames=list(records[0]),
                )
                writer.writeheader()
                writer.writerows(records)

        # Publish without overwriting existing results.
        for temporary_path, destination in zip(
            temporary_paths,
            (operation_output, flow_output),
        ):
            with destination.open("xb") as output:
                published_paths.append(destination)
                with temporary_path.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)

    except Exception:
        # Remove incomplete results created by this execution.
        for path in published_paths:
            path.unlink(missing_ok=True)
        raise

    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)


    print("\nSummary:")
    print(f"Forecast dates: {len(dates)}")
    print(f"Operations: {len(operation_records)}")
    print(f"Flow records: {len(flow_records)}")

    for method in (
        "kerchunk",
        "native_remote",
        "native_download",
        "native_local",
    ):
        values = [
            r["elapsed_seconds"]
            for r in operation_records
            if r["method"] == method
        ]

        print(
            f"{method:18} "
            f"median={statistics.median(values):.3f}s "
            f"min={min(values):.3f}s "
            f"max={max(values):.3f}s"
        )

    print("\nSaved:", operation_output)
    print("Saved:", flow_output)


if __name__ == "__main__":
    main()
