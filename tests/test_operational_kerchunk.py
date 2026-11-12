
"""Offline tests for operational NWM Kerchunk retrieval."""

import errno
import json
from unittest.mock import MagicMock

import numpy as np
import pytest
import xarray as xr

from streamflow_getter.operational_nwm import (
    ForecastConfig,
    prepare_operational_reference,
    read_kerchunk_forecast,
)
from streamflow_getter.reference_cache import RemoteReferenceNotFoundError


@pytest.fixture
def sample_dataset():
    return xr.Dataset(
        {
            "streamflow": (
                "feature_id",
                [7.08, 0.41, 0.0],
            ),
        },
        coords={
            "feature_id": [
                1122645,
                3586192,
                7144704,
            ],
            "time": [np.datetime64("2026-04-19T01:00:00")],
            "reference_time": [
                np.datetime64("2026-04-19T00:00:00")
            ],
        },
    )


@pytest.fixture
def valid_reference():
    url = ForecastConfig().native_url(1)

    return {
        "version": 1,
        "refs": {
            ".zgroup": "{}",
            "feature_id/.zarray": "{}",
            "feature_id/0": [url, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [url, 100, 200],
        },
    }


@pytest.fixture
def mock_kerchunk(monkeypatch, sample_dataset, valid_reference):
    """Replace network and dataset opening with local mocks."""
    import fsspec
    import s3fs

    reference_bytes = json.dumps(valid_reference).encode("utf-8")

    remote_file = MagicMock()
    remote_file.__enter__.return_value.read.return_value = reference_bytes

    s3 = MagicMock()
    s3.open.return_value = remote_file

    monkeypatch.setattr(
        s3fs,
        "S3FileSystem",
        lambda **kwargs: s3,
    )

    filesystem = MagicMock()
    filesystem.get_mapper.return_value = {}

    monkeypatch.setattr(
        fsspec,
        "filesystem",
        lambda *args, **kwargs: filesystem,
    )

    dataset_context = MagicMock()
    dataset_context.__enter__.return_value = sample_dataset

    monkeypatch.setattr(
        xr,
        "open_zarr",
        lambda *args, **kwargs: dataset_context,
    )

    return {
        "s3": s3,
        "filesystem": filesystem,
        "dataset_context": dataset_context,
    }


def test_prepare_reference_without_opening_model_data(
    mock_kerchunk, valid_reference, monkeypatch
):
    import fsspec

    from streamflow_getter import operational_nwm

    config = ForecastConfig()
    raw = json.dumps(valid_reference, indent=2).encode("utf-8")
    remote_file = mock_kerchunk["s3"].open.return_value.__enter__.return_value
    remote_file.read.return_value = raw

    data_access = MagicMock(
        side_effect=AssertionError("Unexpected model data access")
    )
    monkeypatch.setattr(fsspec, "filesystem", data_access)
    monkeypatch.setattr(xr, "open_zarr", data_access)
    monkeypatch.setattr(operational_nwm, "read_native_forecast", data_access)

    prepared = prepare_operational_reference(config, 1)

    assert prepared["reference"] == valid_reference
    assert prepared["reference_json_bytes"] == len(raw)
    assert prepared["source"]["source_product"] == "short_range"
    assert prepared["source"]["native_url"] == config.native_url(1)
    assert prepared["source"]["reference_path"] == config.reference_path(1)
    assert prepared["source"]["lead_hour"] == 1
    mock_kerchunk["s3"].open.assert_called_once_with(
        config.reference_path(1), "rb"
    )
    data_access.assert_not_called()


@pytest.mark.parametrize("cached", [False, True], ids=["uncached", "cached"])
@pytest.mark.parametrize("failure_stage", ["open", "read"])
def test_missing_reference_body_is_classified(
    mock_kerchunk, monkeypatch, tmp_path, cached, failure_stage
):
    from streamflow_getter import reference_cache

    config = ForecastConfig()
    failure = FileNotFoundError(config.reference_path(1))
    s3 = mock_kerchunk["s3"]
    if failure_stage == "open":
        s3.open.side_effect = failure
    else:
        s3.open.return_value.__enter__.return_value.read.side_effect = failure
    monkeypatch.setattr(
        reference_cache, "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-1", "source_generation": "generation-1",
        },
    )

    with pytest.raises(RemoteReferenceNotFoundError, match="body") as caught:
        prepare_operational_reference(
            config, 1, cache_dir=tmp_path if cached else None
        )

    assert caught.value.__cause__ is failure
    assert config.reference_path(1) in str(caught.value)
    assert list(tmp_path.rglob("*.cache.json")) == []
    mock_kerchunk["filesystem"].get_mapper.assert_not_called()
    mock_kerchunk["dataset_context"].__enter__.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        PermissionError(errno.EACCES, "Reference access denied"),
        OSError(errno.EINVAL, "Invalid reference request"),
        TimeoutError("Reference body request timed out"),
    ],
    ids=["permission", "invalid-request", "timeout"],
)
def test_other_reference_body_errors_propagate(
    mock_kerchunk, monkeypatch, tmp_path, failure
):
    from streamflow_getter import reference_cache

    mock_kerchunk["s3"].open.side_effect = failure
    monkeypatch.setattr(
        reference_cache, "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-1", "source_generation": "generation-1",
        },
    )

    with pytest.raises(type(failure)) as caught:
        prepare_operational_reference(ForecastConfig(), 1, cache_dir=tmp_path)

    assert caught.value is failure
    assert list(tmp_path.rglob("*.cache.json")) == []
    mock_kerchunk["dataset_context"].__enter__.assert_not_called()


def test_local_cache_save_missing_path_is_not_reference_missing(
    mock_kerchunk, valid_reference, monkeypatch, tmp_path
):
    from streamflow_getter import reference_cache

    config = ForecastConfig()
    cache_file = (
        tmp_path / config.date_folder / config.product
        / f"{config.filename(1)}.cache.json"
    )
    metadata = {"reference_etag": "etag-old", "source_generation": "generation-1"}
    reference_cache.save_cache_record(
        cache_file,
        reference_cache.create_cache_record(valid_reference, config.native_url(1), metadata),
        config.native_url(1),
    )
    original_bytes = cache_file.read_bytes()
    failure = FileNotFoundError(errno.ENOENT, "Local cache path unavailable", str(cache_file))
    save_record = MagicMock(side_effect=failure)
    monkeypatch.setattr(reference_cache, "save_cache_record", save_record)
    monkeypatch.setattr(
        reference_cache, "fetch_remote_metadata",
        lambda *args, **kwargs: {**metadata, "reference_etag": "etag-new"},
    )

    with pytest.raises(FileNotFoundError) as caught:
        prepare_operational_reference(config, 1, cache_dir=tmp_path)

    assert caught.value is failure
    assert not isinstance(caught.value, RemoteReferenceNotFoundError)
    assert cache_file.read_bytes() == original_bytes
    save_record.assert_called_once()
    mock_kerchunk["dataset_context"].__enter__.assert_not_called()


def test_kerchunk_success(mock_kerchunk):
    result = read_kerchunk_forecast(
        ForecastConfig(),
        1,
        [3586192, 1122645],
    )

    assert result["method"] == "kerchunk"
    assert result["lead_hour"] == 1
    assert result["streamflow_m3s"] == {
        3586192: 0.41,
        1122645: 7.08,
    }

    assert result["valid_time"].startswith("2026-04-19T01:00:00")
    assert result["reference_time"].startswith("2026-04-19T00:00:00")

    mock_kerchunk["dataset_context"].__exit__.assert_called_once()


def test_kerchunk_missing_reach(mock_kerchunk):
    with pytest.raises(ValueError, match="Missing reaches"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [999999],
        )

    mock_kerchunk["dataset_context"].__exit__.assert_called_once()


def test_kerchunk_invalid_reference(
    mock_kerchunk, monkeypatch
):
    from streamflow_getter import reference_validation

    monkeypatch.setattr(
        reference_validation,
        "validate_reference",
        lambda reference: False,
    )

    with pytest.raises(ValueError, match="Invalid Kerchunk"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [3586192],
        )

    mock_kerchunk["s3"].open.assert_called_once()
    mock_kerchunk["dataset_context"].__enter__.assert_not_called()


def test_kerchunk_wrong_source(
    mock_kerchunk, monkeypatch
):
    from streamflow_getter import reference_validation

    monkeypatch.setattr(
        reference_validation,
        "valid_source_identity",
        lambda reference, expected_url: False,
    )

    with pytest.raises(ValueError, match="source identity"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [3586192],
        )

    mock_kerchunk["dataset_context"].__enter__.assert_not_called()


def test_kerchunk_wrong_timestamp(
    mock_kerchunk, sample_dataset
):
    sample_dataset.coords["time"] = [
        np.datetime64("2026-04-19T02:00:00")
    ]

    with pytest.raises(ValueError, match="valid time"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [3586192],
        )

    mock_kerchunk["dataset_context"].__exit__.assert_called_once()


def test_kerchunk_nonfinite_streamflow(
    mock_kerchunk, sample_dataset
):
    sample_dataset["streamflow"].values[1] = np.nan

    with pytest.raises(ValueError, match="Non-finite"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [3586192],
        )

    mock_kerchunk["dataset_context"].__exit__.assert_called_once()



def test_kerchunk_analysis_t0(
    mock_kerchunk,
    sample_dataset,
):
    """Retrieve analysis t0 and preserve its original reference time."""
    import json

    config = ForecastConfig()

    sample_dataset.coords["time"] = [
        np.datetime64("2026-04-19T00:00:00")
    ]
    sample_dataset.coords["reference_time"] = [
        np.datetime64("2026-04-18T21:00:00")
    ]

    url = config.analysis_native_url()

    reference = {
        "version": 1,
        "refs": {
            ".zgroup": "{}",
            "feature_id/.zarray": "{}",
            "feature_id/0": [url, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [url, 100, 200],
        },
    }

    mock_kerchunk["s3"].open.return_value.__enter__.return_value.read.return_value = (
        json.dumps(reference).encode()
    )

    result = read_kerchunk_forecast(
        config,
        0,
        [3586192],
    )

    assert result["product"] == "analysis_assim"
    assert result["lead_hour"] == 0
    assert result["streamflow_m3s"][3586192] == 0.41
    assert result["valid_time"].startswith("2026-04-19T00:00:00")
    assert result["reference_time"].startswith("2026-04-18T21:00:00")

    mock_kerchunk["s3"].open.assert_called_once_with(
        config.analysis_reference_path(),
        "rb",
    )


def test_kerchunk_analysis_t0_rejects_wrong_valid_time(
    mock_kerchunk,
    sample_dataset,
):
    """Reject an analysis file whose valid time differs from the cycle."""
    import json

    config = ForecastConfig()
    url = config.analysis_native_url()

    reference = {
        "version": 1,
        "refs": {
            ".zgroup": "{}",
            "feature_id/.zarray": "{}",
            "feature_id/0": [url, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [url, 100, 200],
        },
    }

    mock_kerchunk["s3"].open.return_value.__enter__.return_value.read.return_value = (
        json.dumps(reference).encode()
    )

    sample_dataset.coords["reference_time"] = [
        np.datetime64("2026-04-18T21:00:00")
    ]

    with pytest.raises(ValueError, match="analysis t0 valid time"):
        read_kerchunk_forecast(
            config,
            0,
            [3586192],
        )

def test_kerchunk_preserves_integer_feature_ids(
    mock_kerchunk,
    monkeypatch,
):
    """Disable masking only for feature_id, not streamflow."""
    import xarray as xr

    captured = {}
    original_open_zarr = xr.open_zarr

    def inspect_open_zarr(*args, **kwargs):
        captured.update(kwargs)
        return original_open_zarr(*args, **kwargs)

    # The existing fixture has already mocked xr.open_zarr.
    monkeypatch.setattr(
        xr,
        "open_zarr",
        inspect_open_zarr,
    )

    result = read_kerchunk_forecast(
        ForecastConfig(),
        1,
        [3586192],
    )

    assert result["method"] == "kerchunk"
    assert captured["mask_and_scale"] == {
        "feature_id": False
    }
