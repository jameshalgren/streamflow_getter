
"""CSV and Parquet output for streamflow time series."""

import os
import tempfile
from pathlib import Path

import pandas as pd


SUPPORTED_FORMATS = {"csv", "parquet"}


def resolve_output_format(path, output_format=None):
    """Resolve CSV or Parquet from an explicit format or file extension."""
    path = Path(path)

    if output_format is not None:
        if not isinstance(output_format, str):
            raise ValueError("Output format must be csv or parquet")

        selected = output_format.lower()

        if selected not in SUPPORTED_FORMATS:
            raise ValueError("Output format must be csv or parquet")

        suffix = path.suffix.lower().lstrip(".")

        if suffix in SUPPORTED_FORMATS and suffix != selected:
            raise ValueError(
                "Output format conflicts with file extension"
            )

        return selected

    suffix = path.suffix.lower().lstrip(".")

    if suffix not in SUPPORTED_FORMATS:
        raise ValueError(
            "Cannot infer output format; use .csv, .parquet, "
            "or specify output_format"
        )

    return suffix


def write_timeseries(
    frame: pd.DataFrame,
    path,
    *,
    output_format=None,
):
    """Safely write a validated time-series DataFrame.

    Existing files are not overwritten. A temporary file is
    serialized first, then published with exclusive creation.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Expected a pandas DataFrame")

    if frame.empty:
        raise ValueError("Cannot write an empty time series")

    destination = Path(path).expanduser()
    selected = resolve_output_format(destination, output_format)

    if destination.exists():
        raise FileExistsError(
            f"Output already exists: {destination}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None
    published = False

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=".streamflow-output-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)

        if selected == "csv":
            frame.to_csv(temporary_path, index=False)
        else:
            frame.to_parquet(
                temporary_path,
                engine="pyarrow",
                index=False,
            )

        with destination.open("xb") as output:
            published = True

            with temporary_path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)

    except Exception:
        if published:
            destination.unlink(missing_ok=True)
        raise

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return destination

def manifest_path_for(output_path):
    """Return the default JSON sidecar path for a data output."""
    from pathlib import Path

    path = Path(output_path).expanduser()

    return path.with_name(
        path.name + ".manifest.json"
    )


def _serialize_manifest(manifest) -> bytes:
    """Serialize one manifest as strict, deterministic UTF-8 JSON."""
    from collections.abc import Mapping
    import json

    if not isinstance(manifest, Mapping):
        raise TypeError(
            "manifest must be a mapping"
        )

    try:
        text = json.dumps(
            dict(manifest),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "manifest must contain strict JSON-compatible values"
        ) from exc

    return (
        text + "\n"
    ).encode("utf-8")


def _publish_manifest_payload(
    payload: bytes,
    destination,
):
    """Atomically expose a fully serialized manifest without overwrite."""
    from pathlib import Path
    import os
    import tempfile

    path = Path(destination).expanduser()

    if path.exists():
        raise FileExistsError(
            f"Manifest already exists: {path}"
        )

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".streamflow-manifest-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(
                temporary.fileno()
            )

            temporary_path = Path(
                temporary.name
            )

        # The temporary file lives in the destination directory.
        # Creating a hard link publishes the complete bytes in one
        # filesystem operation and refuses to overwrite an existing path.
        try:
            os.link(
                temporary_path,
                path,
            )
        except FileExistsError as exc:
            raise FileExistsError(
                f"Manifest already exists: {path}"
            ) from exc

        return path

    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(
                    missing_ok=True
                )
            except OSError:
                # A leaked hidden temporary file is preferable to turning
                # a successfully published manifest into a false failure.
                pass


def write_manifest(
    manifest,
    path,
):
    """Publish a JSON run manifest without overwriting existing output."""
    payload = _serialize_manifest(
        manifest
    )

    return _publish_manifest_payload(
        payload,
        path,
    )


def write_timeseries_with_manifest(
    frame,
    path,
    manifest,
    *,
    output_format=None,
    manifest_path=None,
):
    """Publish streamflow output and its manifest as one logical result.

    Both destination paths are validated before publication. Manifest
    serialization is completed before the data writer starts. If manifest
    publication fails after the data file is created, the newly created
    data file is removed before the original exception is propagated.

    This provides in-process rollback semantics. It is not a portable
    two-file crash-atomic filesystem transaction.
    """
    from pathlib import Path

    data_destination = Path(
        path
    ).expanduser()

    if manifest_path is None:
        manifest_destination = (
            manifest_path_for(
                data_destination
            )
        )
    else:
        manifest_destination = Path(
            manifest_path
        ).expanduser()

    if (
        data_destination
        == manifest_destination
    ):
        raise ValueError(
            "Data and manifest destinations must differ"
        )

    # Validate the requested data format before creating anything.
    resolve_output_format(
        data_destination,
        output_format,
    )

    # Prove the complete manifest is serializable before creating data.
    manifest_payload = _serialize_manifest(
        manifest
    )

    if data_destination.exists():
        raise FileExistsError(
            f"Output already exists: {data_destination}"
        )

    if manifest_destination.exists():
        raise FileExistsError(
            f"Manifest already exists: {manifest_destination}"
        )

    data_written = write_timeseries(
        frame,
        data_destination,
        output_format=output_format,
    )

    try:
        manifest_written = (
            _publish_manifest_payload(
                manifest_payload,
                manifest_destination,
            )
        )

    except Exception as exc:
        try:
            Path(
                data_written
            ).unlink(
                missing_ok=True
            )
        except OSError as cleanup_error:
            try:
                exc.add_note(
                    "Failed to remove data output after "
                    f"manifest publication failure: {cleanup_error}"
                )
            except AttributeError:
                pass

        raise

    return (
        Path(data_written),
        Path(manifest_written),
    )
