
"""Offline tests for Kerchunk-first operational NWM fallback."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from urllib.error import HTTPError

import pytest

from streamflow_getter import operational_nwm
from streamflow_getter.operational_nwm import (
    ForecastConfig,
    fetch_operational_forecast,
)
from streamflow_getter.reference_cache import RemoteReferenceNotFoundError


@pytest.fixture
def config():
    return ForecastConfig()


@pytest.fixture
def expected_result():
    return {
        "method": "kerchunk",
        "streamflow_m3s": {3586192: 0.41},
    }


def test_kerchunk_success_no_fallback(
    monkeypatch, config, expected_result
):
    def native_should_not_run(*args):
        raise AssertionError("Native fallback was not expected")

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        lambda *args: expected_result,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        native_should_not_run,
    )

    result = fetch_operational_forecast(
        config, 1, [3586192]
    )

    assert result["method"] == "kerchunk"


def test_access_failure_uses_native(
    monkeypatch, config, expected_result
):
    def fail_kerchunk(*args):
        raise OSError("Reference unavailable")

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        lambda *args: {
            **expected_result,
            "method": "native_remote",
        },
    )

    result = fetch_operational_forecast(
        config, 1, [3586192]
    )

    assert result["method"] == "native_remote"
    assert "OSError" in result["fallback_reason"]


@pytest.mark.parametrize(
    "message",
    [
        "Incorrect forecast valid time",
        "Missing reaches",
        "Non-finite streamflow values found",
        "Incorrect Kerchunk source identity",
    ],
)
def test_integrity_error_never_falls_back(
    monkeypatch, config, message
):
    def fail_kerchunk(*args):
        raise ValueError(message)

    def native_should_not_run(*args):
        raise AssertionError("Native fallback must not run")

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        native_should_not_run,
    )

    with pytest.raises(ValueError, match=message):
        fetch_operational_forecast(
            config, 1, [3586192]
        )


@pytest.mark.parametrize("cached", [False, True])
def test_both_access_methods_fail(monkeypatch, config, tmp_path, cached):
    kerchunk_error = (
        RemoteReferenceNotFoundError("Reference metadata missing")
        if cached else OSError("Kerchunk unavailable")
    )
    native_error = OSError("Native unavailable")
    native_reader = Mock(side_effect=native_error)

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        Mock(side_effect=kerchunk_error),
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        native_reader,
    )

    with pytest.raises(RuntimeError, match="Both Kerchunk") as caught:
        fetch_operational_forecast(
            config, 1, [3586192],
            cache_dir=tmp_path if cached else None,
        )

    assert caught.value.__cause__ is native_error
    assert caught.value.__notes__ == [
        f"Kerchunk fallback reason: {type(kerchunk_error).__name__}: {kerchunk_error}"
    ]
    native_reader.assert_called_once_with(config, 1, [3586192])


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("Request timed out"),
        ConnectionError("Connection interrupted"),
        FileNotFoundError("Kerchunk reference missing"),
        RemoteReferenceNotFoundError("Kerchunk reference metadata missing"),
    ],
)
def test_recoverable_access_errors_use_native(
    monkeypatch, config, error
):
    """Known access failures should trigger native retrieval."""
    def fail_kerchunk(*args):
        raise error

    def native_success(*args):
        return {
            "method": "native_remote",
            "streamflow_m3s": {3586192: 0.41},
        }

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        native_success,
    )

    result = fetch_operational_forecast(
        config, 1, [3586192]
    )

    assert result["method"] == "native_remote"
    assert type(error).__name__ in result["fallback_reason"]


def test_permission_error_does_not_fallback(monkeypatch, config):
    """Authorization errors must not silently switch sources."""
    def fail_kerchunk(*args):
        raise PermissionError("Access denied")

    def native_should_not_run(*args):
        raise AssertionError("Native fallback must not run")

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        native_should_not_run,
    )

    with pytest.raises(PermissionError, match="Access denied"):
        fetch_operational_forecast(
            config, 1, [3586192]
        )



def test_coordinator_passes_cache_directory(
    monkeypatch, config, tmp_path
):
    """The coordinator forwards the selected cache directory."""
    captured = {}

    def fake_kerchunk(config_arg, hour, reaches, *, cache_dir):
        captured["cache_dir"] = cache_dir
        return {
            "method": "kerchunk",
            "streamflow_m3s": {3586192: 0.41},
        }

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fake_kerchunk,
    )
    native_reader = Mock(side_effect=AssertionError("Unexpected native read"))
    monkeypatch.setattr(operational_nwm, "read_native_forecast", native_reader)

    result = fetch_operational_forecast(
        config,
        1,
        [3586192],
        cache_dir=tmp_path,
    )

    assert result["method"] == "kerchunk"
    assert captured["cache_dir"] == tmp_path
    native_reader.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        OSError("Cached retrieval failed"),
        PermissionError("Reference access denied"),
        TimeoutError("Reference request timed out"),
        ConnectionError("Reference connection interrupted"),
    ],
)
def test_cached_access_failure_does_not_fallback(
    monkeypatch, config, tmp_path, error
):
    """Unclassified cached access errors must not trigger native retrieval."""
    def fail_kerchunk(*args, **kwargs):
        raise error

    def native_should_not_run(*args):
        raise AssertionError("Native fallback must not run")

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        native_should_not_run,
    )

    with pytest.raises(type(error)) as caught:
        fetch_operational_forecast(
            config,
            1,
            [3586192],
            cache_dir=tmp_path,
        )
    assert caught.value is error


@pytest.fixture
def cached_transport(monkeypatch, config, tmp_path):
    """Use real cache/preparation code with offline acquisition boundaries."""
    import fsspec
    import s3fs
    import urllib.request

    from streamflow_getter import reference_cache

    source = operational_nwm.resolve_operational_source(config, 1)
    reference = {
        "version": 1,
        "refs": {
            ".zgroup": "{}",
            "feature_id/.zarray": "{}",
            "feature_id/0": [source["native_url"], 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [source["native_url"], 100, 200],
        },
    }
    cache_file = (
        tmp_path / config.date_folder / source["source_product"]
        / f'{source["filename"]}.cache.json'
    )
    reference_cache.save_cache_record(
        cache_file,
        reference_cache.create_cache_record(
            reference, source["native_url"],
            {"reference_etag": "etag-old", "source_generation": "generation-1"},
        ),
        source["native_url"],
    )
    s3 = MagicMock()
    s3.info.return_value = {"ETag": "etag-new"}
    body = s3.open.return_value.__enter__.return_value
    body.read.return_value = json.dumps(reference).encode()
    monkeypatch.setattr(s3fs, "S3FileSystem", lambda **kwargs: s3)
    head = MagicMock()
    headers = {"x-goog-generation": "generation-1"}
    head.return_value.__enter__.return_value.headers = headers
    monkeypatch.setattr(urllib.request, "urlopen", head)
    arrays = Mock(side_effect=AssertionError("Unexpected model array access"))
    monkeypatch.setattr(fsspec, "filesystem", arrays)
    native = Mock(return_value={
        "method": "native_remote", "streamflow_m3s": {3586192: 0.41},
        "reference_json_bytes": 0,
    })
    monkeypatch.setattr(operational_nwm, "read_native_forecast", native)
    return SimpleNamespace(
        source=source, cache_file=cache_file, original=cache_file.read_bytes(),
        s3=s3, body=body, head=head, headers=headers, arrays=arrays, native=native,
    )


@pytest.mark.parametrize(
    "stage,populated",
    [
        ("metadata", True),
        ("body-open", False),
        ("body-read", True),
        ("metadata-after", True),
        ("metadata-after", False),
    ],
)
def test_missing_remote_reference_uses_cached_native_fallback(
    config, tmp_path, cached_transport, stage, populated
):
    transport = cached_transport
    if not populated:
        transport.cache_file.unlink()
    missing = FileNotFoundError("Reference disappeared")
    if stage == "metadata":
        transport.s3.info.side_effect = missing
    elif stage == "body-open":
        transport.s3.open.side_effect = missing
    elif stage == "body-read":
        transport.body.read.side_effect = missing
    else:
        transport.s3.info.side_effect = [{"ETag": "etag-new"}, missing]

    result = fetch_operational_forecast(config, 1, [3586192], cache_dir=tmp_path)

    transport.native.assert_called_once_with(config, 1, [3586192])
    transport.arrays.assert_not_called()
    assert result["method"] == "native_remote"
    assert result["streamflow_m3s"] == {3586192: 0.41}
    assert result["reference_json_bytes"] == 0
    origin = "metadata" if stage.startswith("metadata") else "body"
    assert result["fallback_reason"] == (
        f"RemoteReferenceNotFoundError: Kerchunk reference {origin} not found: "
        f'{transport.source["reference_path"]}'
    )
    assert transport.s3.info.call_count == (2 if stage == "metadata-after" else 1)
    assert transport.head.call_count == (0 if stage == "metadata" else 1)
    if populated:
        assert transport.cache_file.read_bytes() == transport.original
    else:
        assert not transport.cache_file.exists()


@pytest.mark.parametrize(
    "stage,error_type,message",
    [
        ("source-head", HTTPError, "Not found"),
        ("local-save", FileNotFoundError, "Local cache destination missing"),
        ("source-generation", ValueError, "source generation changed"),
        ("missing-metadata", ValueError, "Missing remote object metadata"),
        ("invalid-json", json.JSONDecodeError, "Expecting property name"),
        ("invalid-reference", ValueError, "Invalid reference structure"),
    ],
)
def test_other_cached_preparation_failures_propagate(
    monkeypatch, config, tmp_path, cached_transport, stage, error_type, message
):
    from streamflow_getter import reference_cache

    transport = cached_transport
    original_error = None
    if stage == "source-head":
        original_error = HTTPError(
            transport.source["native_url"], 404, message, None, None
        )
        transport.head.side_effect = original_error
    elif stage == "local-save":
        original_error = FileNotFoundError(message)
        monkeypatch.setattr(
            reference_cache.os, "replace", Mock(side_effect=original_error)
        )
    elif stage == "source-generation":
        transport.headers["x-goog-generation"] = "generation-2"
    elif stage == "missing-metadata":
        transport.headers.clear()
    elif stage == "invalid-json":
        transport.body.read.return_value = b"{"
    else:
        transport.body.read.return_value = b'{}'

    with pytest.raises(error_type, match=message) as caught:
        fetch_operational_forecast(config, 1, [3586192], cache_dir=tmp_path)

    if original_error is not None:
        assert caught.value is original_error
    transport.native.assert_not_called()
    transport.arrays.assert_not_called()
    assert transport.cache_file.read_bytes() == transport.original
