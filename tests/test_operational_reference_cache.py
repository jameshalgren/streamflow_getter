
"""Tests for production NWM reference caching."""

import errno
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from urllib.error import HTTPError, URLError

import pytest

from streamflow_getter.reference_cache import (
    RemoteReferenceNotFoundError,
    compare_metadata,
    create_cache_record,
    fetch_remote_metadata,
    load_cache_record,
    load_fresh_reference,
    save_cache_record,
    validate_cache_record,
)


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


@pytest.fixture
def metadata():
    return {
        "reference_etag": "etag-1",
        "source_generation": "gen-1",
    }


def test_metadata_unchanged(metadata):
    assert compare_metadata(metadata, metadata.copy()) == "unchanged"


def test_metadata_source_changed(metadata):
    changed = {**metadata, "source_generation": "gen-2"}
    assert compare_metadata(metadata, changed) == "source_changed"


def test_metadata_reference_changed(metadata):
    changed = {**metadata, "reference_etag": "etag-2"}
    assert compare_metadata(metadata, changed) == "reference_changed"


def test_cache_record_roundtrip(tmp_path, valid_reference, metadata):
    path = tmp_path / "record.json"

    record = create_cache_record(valid_reference, URL, metadata)
    save_cache_record(path, record, URL)

    assert load_cache_record(path, URL) == record


def test_corrupted_cache_rejected(tmp_path):
    path = tmp_path / "record.json"
    path.write_text("{invalid json")

    assert load_cache_record(path, URL) is None


def test_wrong_source_rejected(valid_reference, metadata):
    record = create_cache_record(valid_reference, URL, metadata)

    assert not validate_cache_record(
        record,
        "https://example.org/other.nc",
    )


def test_fresh_cache_reused(
    tmp_path, valid_reference, metadata
):
    path = tmp_path / "record.json"

    save_cache_record(
        path,
        create_cache_record(valid_reference, URL, metadata),
        URL,
    )

    def unexpected_download():
        raise AssertionError("Cache should have been reused")

    result = load_fresh_reference(
        path,
        URL,
        lambda: metadata,
        unexpected_download,
    )

    assert result == valid_reference


def test_reference_change_refreshes(
    tmp_path, valid_reference, metadata
):
    path = tmp_path / "record.json"

    old_metadata = {
        **metadata,
        "reference_etag": "etag-old",
    }

    save_cache_record(
        path,
        create_cache_record(valid_reference, URL, old_metadata),
        URL,
    )

    result = load_fresh_reference(
        path,
        URL,
        lambda: metadata,
        lambda: json.dumps(valid_reference).encode(),
    )

    assert result == valid_reference

    updated = load_cache_record(path, URL)
    assert updated["manifest"]["reference_etag"] == "etag-1"


def test_source_generation_change_rejected(
    tmp_path, valid_reference, metadata
):
    path = tmp_path / "record.json"

    save_cache_record(
        path,
        create_cache_record(valid_reference, URL, metadata),
        URL,
    )

    changed = {
        **metadata,
        "source_generation": "gen-2",
    }

    with pytest.raises(ValueError, match="generation changed"):
        load_fresh_reference(
            path,
            URL,
            lambda: changed,
            lambda: json.dumps(valid_reference).encode(),
        )


def test_failed_refresh_preserves_record(
    tmp_path, valid_reference, metadata
):
    path = tmp_path / "record.json"

    save_cache_record(
        path,
        create_cache_record(valid_reference, URL, metadata),
        URL,
    )

    original = path.read_bytes()

    changed = {
        **metadata,
        "reference_etag": "etag-2",
    }

    def failed_download():
        raise ConnectionError("Download failed")

    with pytest.raises(ConnectionError):
        load_fresh_reference(
            path,
            URL,
            lambda: changed,
            failed_download,
        )

    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "error_type,error_number",
    [
        (PermissionError, errno.EACCES),
        (IsADirectoryError, errno.EISDIR),
        (OSError, errno.EIO),
    ],
    ids=["permission", "directory", "io"],
)
def test_cache_read_io_error_stops_refresh_and_preserves_record(
    tmp_path, monkeypatch, valid_reference, metadata,
    error_type, error_number,
):
    path = tmp_path / "record.json"
    save_cache_record(
        path,
        create_cache_record(valid_reference, URL, metadata),
        URL,
    )
    original_bytes = path.read_bytes()
    failure = error_type(error_number, "Cache read failed", str(path))
    original_open = Path.open
    downloader = Mock(side_effect=AssertionError("Unexpected reference download"))

    def fail_cache_read(candidate, *args, **kwargs):
        if candidate == path:
            raise failure
        return original_open(candidate, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, "open", fail_cache_read)
        with pytest.raises(error_type) as caught:
            load_fresh_reference(path, URL, lambda: metadata, downloader)
        assert caught.value is failure
        downloader.assert_not_called()

    assert path.read_bytes() == original_bytes


def test_invalid_download_rejected(tmp_path, metadata):
    path = tmp_path / "record.json"

    with pytest.raises(ValueError):
        load_fresh_reference(
            path,
            URL,
            lambda: metadata,
            lambda: b'{"version":1,"refs":{}}',
        )

    assert not path.exists()



def test_fetch_remote_metadata(monkeypatch):
    """Read reference ETag and source generation."""
    from unittest.mock import MagicMock
    import urllib.request

    from streamflow_getter.reference_cache import fetch_remote_metadata

    s3 = MagicMock()
    s3.info.return_value = {"ETag": "etag-123"}

    response = MagicMock()
    response.headers.get.return_value = "generation-456"

    context = MagicMock()
    context.__enter__.return_value = response

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: context,
    )

    result = fetch_remote_metadata(
        "bucket/reference.json",
        URL,
        s3=s3,
    )

    assert result == {
        "reference_etag": "etag-123",
        "source_generation": "generation-456",
    }

    s3.info.assert_called_once_with("bucket/reference.json", refresh=True)


@pytest.mark.parametrize("listing_state", ["stale-etag", "stale-absence"])
def test_stale_s3_listing_cannot_hide_reference_refresh(
    tmp_path, monkeypatch, valid_reference, metadata, listing_state
):
    from contextlib import nullcontext
    from types import SimpleNamespace
    import urllib.request

    import s3fs

    reference_path = "bucket/references/reference.json"
    cache_file = tmp_path / "record.json"
    save_cache_record(
        cache_file, create_cache_record(valid_reference, URL, metadata), URL
    )
    original_bytes = cache_file.read_bytes()
    updated_reference = {
        **valid_reference,
        "refs": {**valid_reference["refs"], ".zattrs": '{"revision":"updated"}'},
    }
    raw = json.dumps(updated_reference).encode("utf-8")
    current_etag = "etag-2"

    s3 = s3fs.S3FileSystem(anon=True, skip_instance_cache=True)
    s3.dircache["bucket/references"] = (
        [{"name": reference_path, "type": "file", "size": 1,
          "ETag": metadata["reference_etag"]}]
        if listing_state == "stale-etag" else []
    )

    async def current_reference_metadata(operation, *args, **kwargs):
        assert operation == "head_object"
        assert kwargs["Bucket"] == "bucket"
        assert kwargs["Key"] == "references/reference.json"
        return {"ETag": current_etag, "ContentLength": len(raw)}

    call_s3 = AsyncMock(side_effect=current_reference_metadata)
    monkeypatch.setattr(s3, "_call_s3", call_s3)
    response = SimpleNamespace(
        headers={"x-goog-generation": metadata["source_generation"]}
    )
    source_head = Mock(return_value=nullcontext(response))
    monkeypatch.setattr(urllib.request, "urlopen", source_head)

    def download_reference():
        with s3.open(reference_path, "rb") as remote_file:
            assert remote_file.details["ETag"] == current_etag
            assert remote_file.size == len(raw)
        return raw

    downloader = Mock(side_effect=download_reference)

    result = load_fresh_reference(
        cache_file, URL,
        lambda: fetch_remote_metadata(reference_path, URL, s3=s3),
        downloader,
    )

    assert result == updated_reference
    cached = load_cache_record(cache_file, URL)
    assert cached is not None
    assert cached["reference"] == updated_reference
    assert cached["manifest"]["reference_etag"] == current_etag
    assert cached["manifest"]["source_generation"] == metadata["source_generation"]
    assert cache_file.read_bytes() != original_bytes
    downloader.assert_called_once_with()
    assert call_s3.await_count == 3
    assert source_head.call_count == 2


def test_missing_reference_metadata_is_classified(monkeypatch):
    import urllib.request

    reference_path = "bucket/reference.json"
    failure = FileNotFoundError(reference_path)
    s3 = Mock()
    s3.info.side_effect = failure
    source_head = Mock(side_effect=AssertionError("Unexpected source HEAD"))
    monkeypatch.setattr(urllib.request, "urlopen", source_head)

    with pytest.raises(RemoteReferenceNotFoundError, match="metadata") as caught:
        fetch_remote_metadata(reference_path, URL, s3=s3)

    assert caught.value.__cause__ is failure
    assert reference_path in str(caught.value)
    source_head.assert_not_called()
    s3.open.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        PermissionError(errno.EACCES, "Reference access denied"),
        OSError(errno.EINVAL, "Invalid reference request"),
        TimeoutError("Reference metadata request timed out"),
    ],
    ids=["permission", "invalid-request", "timeout"],
)
def test_other_reference_metadata_errors_propagate(monkeypatch, failure):
    import urllib.request

    s3 = Mock()
    s3.info.side_effect = failure
    source_head = Mock(side_effect=AssertionError("Unexpected source HEAD"))
    monkeypatch.setattr(urllib.request, "urlopen", source_head)

    with pytest.raises(type(failure)) as caught:
        fetch_remote_metadata("bucket/reference.json", URL, s3=s3)

    assert caught.value is failure
    source_head.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        HTTPError(URL, 403, "Forbidden", {}, None),
        HTTPError(URL, 404, "Not Found", {}, None),
        URLError(TimeoutError("Source metadata request timed out")),
        FileNotFoundError("Native source metadata unavailable"),
    ],
    ids=["http-403", "http-404", "url-error", "file-not-found"],
)
def test_source_head_errors_are_not_reference_missing(monkeypatch, failure):
    import urllib.request

    s3 = Mock()
    s3.info.return_value = {"ETag": "etag-1"}
    source_head = Mock(side_effect=failure)
    monkeypatch.setattr(urllib.request, "urlopen", source_head)

    with pytest.raises(type(failure)) as caught:
        fetch_remote_metadata("bucket/reference.json", URL, s3=s3)

    assert caught.value is failure
    assert not isinstance(caught.value, RemoteReferenceNotFoundError)
    source_head.assert_called_once()
    s3.open.assert_not_called()


def test_fetch_remote_metadata_missing_generation(monkeypatch):
    """Missing source-generation metadata must be rejected."""
    from unittest.mock import MagicMock
    import urllib.request

    from streamflow_getter.reference_cache import fetch_remote_metadata

    s3 = MagicMock()
    s3.info.return_value = {"ETag": "etag-123"}

    response = MagicMock()
    response.headers.get.return_value = None

    context = MagicMock()
    context.__enter__.return_value = response

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: context,
    )

    with pytest.raises(ValueError, match="Missing remote"):
        fetch_remote_metadata(
            "bucket/reference.json",
            URL,
            s3=s3,
        )


def test_fetch_remote_metadata_missing_etag(monkeypatch):
    """Missing reference ETag must be rejected."""
    from unittest.mock import MagicMock
    import urllib.request

    from streamflow_getter.reference_cache import fetch_remote_metadata

    s3 = MagicMock()
    s3.info.return_value = {}

    response = MagicMock()
    response.headers.get.return_value = "generation-456"

    context = MagicMock()
    context.__enter__.return_value = response

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: context,
    )

    with pytest.raises(ValueError, match="Missing remote"):
        fetch_remote_metadata(
            "bucket/reference.json",
            URL,
            s3=s3,
        )

def test_metadata_missing_returns_unknown(metadata):
    current = metadata.copy()
    del current["source_generation"]

    assert compare_metadata(metadata, current) == "unknown"


def test_source_change_takes_priority_over_reference_change(metadata):
    current = {
        **metadata,
        "reference_etag": "etag-2",
        "source_generation": "gen-2",
    }

    assert compare_metadata(metadata, current) == "source_changed"

def test_metadata_change_during_download_rejected(
    tmp_path, valid_reference, metadata
):
    """Reject a reference if remote metadata changes during download."""
    path = tmp_path / "record.json"

    before = metadata.copy()
    after = {
        **metadata,
        "reference_etag": "etag-changed",
    }

    snapshots = iter([before, after])

    def metadata_provider():
        return next(snapshots)

    def downloader():
        return json.dumps(valid_reference).encode("utf-8")

    with pytest.raises(ValueError, match="changed during download"):
        load_fresh_reference(
            path,
            URL,
            metadata_provider,
            downloader,
        )

    assert not path.exists()

def test_corrupted_cache_is_refreshed(
    tmp_path, valid_reference, metadata
):
    """Replace a corrupted cache with a validated reference."""
    path = tmp_path / "record.json"
    path.write_text("{invalid json", encoding="utf-8")

    result = load_fresh_reference(
        path,
        URL,
        lambda: metadata,
        lambda: json.dumps(valid_reference).encode("utf-8"),
    )

    assert result == valid_reference

    cached = load_cache_record(path, URL)

    assert cached is not None
    assert cached["reference"] == valid_reference

def test_wrong_source_cache_is_refreshed(
    tmp_path, valid_reference, metadata
):
    """Replace cached references pointing to an incorrect source."""
    path = tmp_path / "record.json"

    wrong_reference = json.loads(json.dumps(valid_reference))
    wrong_reference["refs"]["streamflow/0"][0] = (
        "https://example.org/wrong.nc"
    )

    path.write_text(
        json.dumps({
            "reference": wrong_reference,
            "manifest": {},
        }),
        encoding="utf-8",
    )

    result = load_fresh_reference(
        path,
        URL,
        lambda: metadata,
        lambda: json.dumps(valid_reference).encode("utf-8"),
    )

    assert result == valid_reference

    cached = load_cache_record(path, URL)
    assert cached is not None
    assert cached["reference"] == valid_reference
