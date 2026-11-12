"""Tests for experimental Kerchunk reference caching."""

import json

import pytest

from streamflow_getter.reference_cache import load_fresh_reference
from streamflow_getter.reference_cache import create_cache_record, save_cache_record


URL = "https://example.org/data.nc"


@pytest.fixture
def valid_reference():
    return {
        "version": 1,
        "refs": {
            ".zgroup": '{"zarr_format":2}',
            "feature_id/.zarray": "{}",
            "feature_id/0": [URL, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [URL, 100, 200],
        },
    }


def test_fresh_cache_reused(tmp_path, valid_reference):
    path = tmp_path / "record.json"
    metadata = {
        "reference_etag": "etag-1",
        "source_generation": "gen-1",
    }

    record = create_cache_record(valid_reference, URL, metadata)
    save_cache_record(path, record, URL)

    def downloader():
        raise AssertionError("Unexpected download")

    result = load_fresh_reference(
        path, URL, lambda: metadata, downloader
    )

    assert result == valid_reference


def test_reference_change_refreshes(tmp_path, valid_reference):
    path = tmp_path / "record.json"
    old = {
        "reference_etag": "etag-old",
        "source_generation": "gen-1",
    }
    current = {
        "reference_etag": "etag-new",
        "source_generation": "gen-1",
    }

    save_cache_record(
        path,
        create_cache_record(valid_reference, URL, old),
        URL,
    )

    result = load_fresh_reference(
        path,
        URL,
        lambda: current,
        lambda: json.dumps(valid_reference).encode(),
    )

    assert result == valid_reference


def test_source_change_rejected(tmp_path, valid_reference):
    path = tmp_path / "record.json"
    old = {
        "reference_etag": "etag-1",
        "source_generation": "gen-1",
    }
    current = {
        "reference_etag": "etag-1",
        "source_generation": "gen-2",
    }

    save_cache_record(
        path,
        create_cache_record(valid_reference, URL, old),
        URL,
    )

    with pytest.raises(ValueError, match="generation changed"):
        load_fresh_reference(
            path,
            URL,
            lambda: current,
            lambda: json.dumps(valid_reference).encode(),
        )


def test_missing_remote_metadata_rejected(tmp_path):
    with pytest.raises(ValueError, match="incomplete"):
        load_fresh_reference(
            tmp_path / "record.json",
            URL,
            lambda: {"reference_etag": "etag-1"},
            lambda: b"{}",
        )


def test_metadata_changes_during_download(
    tmp_path, valid_reference
):
    path = tmp_path / "record.json"

    before = {
        "reference_etag": "etag-before",
        "source_generation": "gen-1",
    }

    after = {
        "reference_etag": "etag-after",
        "source_generation": "gen-1",
    }

    calls = iter([before, after])

    def metadata_provider():
        return next(calls)

    def downloader():
        return json.dumps(valid_reference).encode()

    with pytest.raises(ValueError, match="changed during download"):
        load_fresh_reference(
            path,
            URL,
            metadata_provider,
            downloader,
        )

    assert not path.exists()



def test_failed_refresh_preserves_valid_record(
    tmp_path, valid_reference
):
    path = tmp_path / "record.json"

    old_metadata = {
        "reference_etag": "etag-old",
        "source_generation": "gen-1",
    }

    new_metadata = {
        "reference_etag": "etag-new",
        "source_generation": "gen-1",
    }

    record = create_cache_record(
        valid_reference,
        URL,
        old_metadata,
    )

    save_cache_record(path, record, URL)

    original_bytes = path.read_bytes()

    def downloader():
        raise ConnectionError("Download failed")

    with pytest.raises(ConnectionError, match="Download failed"):
        load_fresh_reference(
            path,
            URL,
            lambda: new_metadata,
            downloader,
        )

    assert path.read_bytes() == original_bytes

def test_fresh_loader_replaces_corrupt_record(
    tmp_path, valid_reference
):
    path = tmp_path / "record.json"
    path.write_text("{invalid json")

    metadata = {
        "reference_etag": "etag-1",
        "source_generation": "gen-1",
    }

    result = load_fresh_reference(
        path,
        URL,
        lambda: metadata,
        lambda: json.dumps(valid_reference).encode(),
    )

    assert result == valid_reference

    from streamflow_getter.reference_cache import load_cache_record

    assert load_cache_record(path, URL) is not None


def test_fresh_loader_replaces_wrong_source(
    tmp_path, valid_reference
):
    path = tmp_path / "record.json"

    metadata = {
        "reference_etag": "etag-1",
        "source_generation": "gen-1",
    }

    wrong_reference = json.loads(json.dumps(valid_reference))
    wrong_reference["refs"]["streamflow/0"][0] = (
        "https://example.org/wrong.nc"
    )

    path.write_text(json.dumps({
        "reference": wrong_reference,
        "manifest": {},
    }))

    result = load_fresh_reference(
        path,
        URL,
        lambda: metadata,
        lambda: json.dumps(valid_reference).encode(),
    )

    assert result == valid_reference


def test_fresh_loader_rejects_invalid_download(tmp_path):
    path = tmp_path / "record.json"

    metadata = {
        "reference_etag": "etag-1",
        "source_generation": "gen-1",
    }

    with pytest.raises(ValueError):
        load_fresh_reference(
            path,
            URL,
            lambda: metadata,
            lambda: b'{"version":1,"refs":{}}',
        )

    assert not path.exists()
