"""Validated reference caching for operational NWM forecasts."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .reference_validation import (
    validate_reference,
    valid_source_identity,
)


class RemoteReferenceNotFoundError(FileNotFoundError):
    """A remote Kerchunk reference object was not found.

    Raised only at reference metadata/body acquisition boundaries. The
    original FileNotFoundError is retained as the exception's __cause__.
    Native-source, local-cache, and validation errors are not classified here.
    """


def compare_metadata(cached, current):
    """Return a freshness status for two metadata snapshots.

    Both dictionaries must contain:
    - reference_etag
    - source_generation
    """
    required = ("reference_etag", "source_generation")

    for key in required:
        if not cached.get(key) or not current.get(key):
            return "unknown"

    if cached["source_generation"] != current["source_generation"]:
        return "source_changed"

    if cached["reference_etag"] != current["reference_etag"]:
        return "reference_changed"

    return "unchanged"


def sha256_bytes(data):
    """Return SHA-256 digest of reference JSON bytes."""
    return hashlib.sha256(data).hexdigest()


def create_manifest(reference_bytes, expected_url, metadata):
    """Create a manifest for a validated reference."""
    if not isinstance(reference_bytes, bytes):
        raise TypeError("reference_bytes must be bytes")

    if not isinstance(expected_url, str) or not expected_url:
        raise ValueError("expected_url is required")

    required = ("reference_etag", "source_generation")

    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a dictionary")

    if any(not metadata.get(key) for key in required):
        raise ValueError("Required metadata is missing")

    return {
        "schema_version": 1,
        "source_url": expected_url,
        "reference_sha256": sha256_bytes(reference_bytes),
        "reference_etag": metadata["reference_etag"],
        "source_generation": str(metadata["source_generation"]),
    }


def validate_manifest(manifest, reference_bytes, expected_url):
    """Validate manifest structure, identity, and local digest."""
    if not isinstance(manifest, dict):
        return False

    if manifest.get("schema_version") != 1:
        return False

    if manifest.get("source_url") != expected_url:
        return False

    if not isinstance(reference_bytes, bytes):
        return False

    if not manifest.get("reference_etag"):
        return False

    if not manifest.get("source_generation"):
        return False

    return manifest.get("reference_sha256") == sha256_bytes(
        reference_bytes
    )


def create_cache_record(reference, expected_url, metadata):
    """Bundle a validated reference and its metadata."""

    if not validate_reference(reference):
        raise ValueError("Invalid reference structure")

    if not valid_source_identity(reference, expected_url):
        raise ValueError("Incorrect reference source")

    raw = json.dumps(
        reference, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    manifest = create_manifest(raw, expected_url, metadata)

    return {
        "manifest": manifest,
        "reference": reference,
    }


def validate_cache_record(record, expected_url):
    """Validate a complete cached reference record."""

    if not isinstance(record, dict):
        return False

    reference = record.get("reference")
    manifest = record.get("manifest")

    if not validate_reference(reference):
        return False

    if not valid_source_identity(reference, expected_url):
        return False

    raw = json.dumps(
        reference, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    return validate_manifest(manifest, raw, expected_url)


def save_cache_record(path, record, expected_url):
    """Atomically save a validated single-file cache record."""
    if not validate_cache_record(record, expected_url):
        raise ValueError("Invalid cache record")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".cache-record-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(record, temporary, sort_keys=True)

        os.replace(temporary_path, path)

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_cache_record(path, expected_url):
    """Return a validated record, or None if it is missing or invalid.

    Other local filesystem errors propagate so callers can distinguish
    storage failures from recoverable cache misses.
    """
    path = Path(path)

    try:
        with path.open("r", encoding="utf-8") as file:
            record = json.load(file)

        if validate_cache_record(record, expected_url):
            return record

    except (FileNotFoundError, UnicodeError, ValueError, TypeError):
        pass

    return None


def load_fresh_reference(
    cache_file,
    expected_url,
    metadata_provider,
    downloader,
):
    """Load a reference only when its source metadata is consistent.

    metadata_provider returns current reference_etag and source_generation.
    downloader returns the Kerchunk reference JSON bytes.
    """

    current = metadata_provider()

    if not isinstance(current, dict):
        raise ValueError("Invalid remote metadata")

    required = ("reference_etag", "source_generation")
    if any(not current.get(key) for key in required):
        raise ValueError("Remote metadata is incomplete")

    current = {
        "reference_etag": current["reference_etag"],
        "source_generation": str(current["source_generation"]),
    }

    record = load_cache_record(cache_file, expected_url)

    if record is not None:
        status = compare_metadata(record["manifest"], current)

        if status == "unchanged":
            return record["reference"]

        if status == "source_changed":
            raise ValueError(
                "NWM source generation changed; "
                "reference compatibility must be verified"
            )

        if status == "unknown":
            raise ValueError("Cannot establish cache freshness")

    raw = downloader()

    if isinstance(raw, bytes):
        reference = json.loads(raw)
    elif isinstance(raw, str):
        reference = json.loads(raw)
    else:
        raise TypeError("Downloader must return JSON bytes or text")

    # Check whether remote metadata changed during the download.
    after = metadata_provider()

    if not isinstance(after, dict):
        raise ValueError("Remote metadata is incomplete")

    required = ("reference_etag", "source_generation")

    if any(not after.get(key) for key in required):
        raise ValueError("Remote metadata is incomplete")

    after = {
        "reference_etag": after["reference_etag"],
        "source_generation": str(after["source_generation"]),
    }

    if compare_metadata(current, after) != "unchanged":
        raise ValueError(
            "Remote metadata changed during download"
        )

    new_record = create_cache_record(
        reference,
        expected_url,
        current,
    )

    save_cache_record(cache_file, new_record, expected_url)

    return new_record["reference"]



def fetch_remote_metadata(
    reference_path: str,
    source_url: str,
    *,
    s3=None,
) -> dict[str, str]:
    """Retrieve remote metadata required for NWM cache freshness.

    Uses the reference object's S3 ETag and the source NetCDF
    object's GCS generation header. Clear S3 listing metadata for this path
    before requesting fresh object metadata, including for later body opens.
    """
    import urllib.request

    import s3fs

    if s3 is None:
        s3 = s3fs.S3FileSystem(
            anon=True,
            skip_instance_cache=True,
        )

    # Later body opens must not reuse an old listing's size or ETag either.
    s3.invalidate_cache(reference_path)
    try:
        reference_info = s3.info(reference_path, refresh=True)
    except FileNotFoundError as exc:
        raise RemoteReferenceNotFoundError(
            f"Kerchunk reference metadata not found: {reference_path}"
        ) from exc

    request = urllib.request.Request(
        source_url,
        method="HEAD",
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        generation = response.headers.get("x-goog-generation")

    etag = reference_info.get("ETag")

    if not etag or not generation:
        raise ValueError("Missing remote object metadata")

    return {
        "reference_etag": str(etag),
        "source_generation": str(generation),
    }
