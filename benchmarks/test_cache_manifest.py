"""Tests for reference-cache metadata manifests."""
"""Tests for reference-cache metadata manifests."""

import json

import pytest

from streamflow_getter.reference_cache import (
    create_manifest,
    validate_manifest,
    create_cache_record,
    validate_cache_record,
    save_cache_record,
    load_cache_record,
)

URL = "https://example.org/data.nc"

METADATA = {
    "reference_etag": "etag-123",
    "source_generation": "generation-456",
}


def test_create_and_validate_manifest():
    raw = b'{"version":1,"refs":{}}'

    manifest = create_manifest(raw, URL, METADATA)

    assert validate_manifest(manifest, raw, URL)


def test_corrupted_reference_rejected():
    raw = b'{"version":1,"refs":{}}'
    manifest = create_manifest(raw, URL, METADATA)

    assert not validate_manifest(manifest, raw + b"corrupt", URL)


def test_wrong_source_rejected():
    raw = b"reference"
    manifest = create_manifest(raw, URL, METADATA)

    assert not validate_manifest(
        manifest,
        raw,
        "https://example.org/other.nc",
    )


def test_missing_metadata_rejected():
    with pytest.raises(ValueError):
        create_manifest(
            b"reference",
            URL,
            {"reference_etag": "etag-123"},
        )


def test_invalid_schema_rejected():
    raw = b"reference"
    manifest = create_manifest(raw, URL, METADATA)
    manifest["schema_version"] = 99

    assert not validate_manifest(manifest, raw, URL)





def test_single_record_valid():
    reference = {
        "version": 1,
        "refs": {
            ".zgroup": '{"zarr_format":2}',
            "feature_id/.zarray": "{}",
            "feature_id/0": [URL, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [URL, 100, 200],
        },
    }

    record = create_cache_record(reference, URL, METADATA)

    assert validate_cache_record(record, URL)


def test_single_record_wrong_source():
    reference = {
        "version": 1,
        "refs": {
            ".zgroup": '{"zarr_format":2}',
            "feature_id/.zarray": "{}",
            "feature_id/0": [URL, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [URL, 100, 200],
        },
    }

    record = create_cache_record(reference, URL, METADATA)

    assert not validate_cache_record(
        record, "https://example.org/other.nc"
    )


def test_single_record_corruption():
    reference = {
        "version": 1,
        "refs": {
            ".zgroup": '{"zarr_format":2}',
            "feature_id/.zarray": "{}",
            "feature_id/0": [URL, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [URL, 100, 200],
        },
    }

    record = create_cache_record(reference, URL, METADATA)
    record["reference"]["refs"]["streamflow/0"][2] = 999

    assert not validate_cache_record(record, URL)

def test_save_and_load_single_record(tmp_path):
    reference = {
        "version": 1,
        "refs": {
            ".zgroup": '{"zarr_format":2}',
            "feature_id/.zarray": "{}",
            "feature_id/0": [URL, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [URL, 100, 200],
        },
    }

    record = create_cache_record(reference, URL, METADATA)
    path = tmp_path / "cache-record.json"

    save_cache_record(path, record, URL)

    assert path.exists()
    assert load_cache_record(path, URL) == record


def test_invalid_record_not_saved(tmp_path):
    path = tmp_path / "cache-record.json"

    with pytest.raises(ValueError):
        save_cache_record(path, {"invalid": True}, URL)

    assert not path.exists()


def test_corrupted_record_rejected(tmp_path):
    path = tmp_path / "cache-record.json"
    path.write_text("{invalid json")

    assert load_cache_record(path, URL) is None


def test_wrong_source_record_rejected(tmp_path):
    reference = {
        "version": 1,
        "refs": {
            ".zgroup": '{"zarr_format":2}',
            "feature_id/.zarray": "{}",
            "feature_id/0": [URL, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [URL, 100, 200],
        },
    }

    record = create_cache_record(reference, URL, METADATA)
    path = tmp_path / "cache-record.json"

    save_cache_record(path, record, URL)

    assert load_cache_record(
        path, "https://example.org/other.nc"
    ) is None