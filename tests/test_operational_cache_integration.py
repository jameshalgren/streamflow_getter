
"""Offline integration tests for cached operational Kerchunk retrieval."""

import json
from unittest.mock import MagicMock, call

import numpy as np
import pytest
import xarray as xr

from streamflow_getter.operational_nwm import (
    ForecastConfig,
    prepare_operational_reference,
    prepare_operational_references,
    read_kerchunk_forecast,
    resolve_operational_source,
)


def test_cached_kerchunk_reuses_reference(tmp_path, monkeypatch):
    import fsspec
    import s3fs

    from streamflow_getter import operational_nwm, reference_cache

    config = ForecastConfig()
    url = config.native_url(1)

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

    raw = json.dumps(reference).encode()

    s3 = MagicMock()
    remote_context = MagicMock()
    remote_context.__enter__.return_value.read.return_value = raw
    s3.open.return_value = remote_context

    monkeypatch.setattr(
        s3fs,
        "S3FileSystem",
        lambda **kwargs: s3,
    )

    monkeypatch.setattr(
        reference_cache,
        "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-1",
            "source_generation": "gen-1",
        },
    )

    filesystem = MagicMock()
    filesystem.get_mapper.return_value = {}
    make_filesystem = MagicMock(return_value=filesystem)

    monkeypatch.setattr(
        fsspec,
        "filesystem",
        make_filesystem,
    )

    ds = xr.Dataset(
        {
            "streamflow": (
                "feature_id",
                [0.41],
            ),
        },
        coords={
            "feature_id": [3586192],
            "time": [np.datetime64("2026-04-19T01:00:00")],
            "reference_time": [
                np.datetime64("2026-04-19T00:00:00")
            ],
        },
    )

    dataset_context = MagicMock()
    dataset_context.__enter__.return_value = ds
    open_dataset = MagicMock(return_value=dataset_context)

    monkeypatch.setattr(
        xr,
        "open_zarr",
        open_dataset,
    )

    native_reader = MagicMock(side_effect=AssertionError("Unexpected native read"))
    monkeypatch.setattr(operational_nwm, "read_native_forecast", native_reader)

    prepared = prepare_operational_references(
        [config], 1, 1, cache_dir=tmp_path, include_t0=False
    )
    cache_file = (
        tmp_path
        / "nwm.20260419"
        / "short_range"
        / f"{config.filename(1)}.cache.json"
    )
    cached = reference_cache.load_cache_record(cache_file, url)

    assert cached is not None
    assert cached["reference"] == reference
    assert len(prepared) == 1
    assert prepared[0]["source"] == resolve_operational_source(config, 1)
    assert prepared[0]["reference_json_bytes"] == len(raw)
    assert "reference" not in prepared[0]
    make_filesystem.assert_not_called()
    open_dataset.assert_not_called()
    native_reader.assert_not_called()

    first = read_kerchunk_forecast(
        config,
        1,
        [3586192],
        cache_dir=tmp_path,
    )

    second = read_kerchunk_forecast(
        config,
        1,
        [3586192],
        cache_dir=tmp_path,
    )

    assert first["streamflow_m3s"] == second["streamflow_m3s"]
    assert first["streamflow_m3s"][3586192] == 0.41

    # The reference JSON should only be downloaded once.
    assert s3.open.call_count == 1


def test_cached_reader_rejects_source_generation_change(
    tmp_path, monkeypatch
):
    """A changed source generation must stop cached retrieval."""
    from streamflow_getter import reference_cache
    from streamflow_getter.reference_cache import (
        create_cache_record,
        save_cache_record,
    )

    config = ForecastConfig()
    url = config.native_url(1)

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

    cache_file = (
        tmp_path
        / config.date_folder
        / config.product
        / f"{config.filename(1)}.cache.json"
    )

    save_cache_record(
        cache_file,
        create_cache_record(
            reference,
            url,
            {
                "reference_etag": "etag-1",
                "source_generation": "generation-1",
            },
        ),
        url,
    )

    monkeypatch.setattr(
        reference_cache,
        "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-1",
            "source_generation": "generation-2",
        },
    )

    with pytest.raises(ValueError, match="generation changed"):
        read_kerchunk_forecast(
            config,
            1,
            [3586192],
            cache_dir=tmp_path,
        )


def test_cached_reader_rejects_missing_metadata(
    tmp_path, monkeypatch
):
    """Incomplete metadata must not be treated as fresh."""
    from streamflow_getter import reference_cache

    monkeypatch.setattr(
        reference_cache,
        "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-1",
        },
    )

    with pytest.raises(ValueError, match="incomplete"):
        read_kerchunk_forecast(
            ForecastConfig(),
            1,
            [3586192],
            cache_dir=tmp_path,
        )



def test_cached_reader_refreshes_changed_reference(
    tmp_path, monkeypatch
):
    """A changed reference ETag refreshes the cached record."""
    import json
    from unittest.mock import MagicMock

    import fsspec
    import s3fs
    import xarray as xr

    from streamflow_getter import reference_cache
    from streamflow_getter.reference_cache import (
        create_cache_record,
        load_cache_record,
        save_cache_record,
    )

    config = ForecastConfig()
    url = config.native_url(1)

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

    cache_file = (
        tmp_path
        / config.date_folder
        / config.product
        / f"{config.filename(1)}.cache.json"
    )

    save_cache_record(
        cache_file,
        create_cache_record(
            reference,
            url,
            {
                "reference_etag": "etag-old",
                "source_generation": "gen-1",
            },
        ),
        url,
    )

    monkeypatch.setattr(
        reference_cache,
        "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-new",
            "source_generation": "gen-1",
        },
    )

    s3 = MagicMock()
    remote_context = MagicMock()
    remote_context.__enter__.return_value.read.return_value = (
        json.dumps(reference).encode()
    )
    s3.open.return_value = remote_context

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

    ds = xr.Dataset(
        {
            "streamflow": (
                "feature_id",
                [0.41],
            ),
        },
        coords={
            "feature_id": [3586192],
            "time": [np.datetime64("2026-04-19T01:00:00")],
            "reference_time": [
                np.datetime64("2026-04-19T00:00:00")
            ],
        },
    )

    dataset_context = MagicMock()
    dataset_context.__enter__.return_value = ds

    monkeypatch.setattr(
        xr,
        "open_zarr",
        lambda *args, **kwargs: dataset_context,
    )

    result = read_kerchunk_forecast(
        config,
        1,
        [3586192],
        cache_dir=tmp_path,
    )

    assert result["streamflow_m3s"][3586192] == 0.41
    assert result["method"] == "kerchunk"

    updated = load_cache_record(cache_file, url)

    assert updated is not None
    assert updated["manifest"]["reference_etag"] == "etag-new"
    assert updated["manifest"]["source_generation"] == "gen-1"

    s3.open.assert_called_once()



@pytest.mark.parametrize(
    "product,forecast_hour,analysis_product",
    [
        ("short_range", 1, "analysis_assim"),
        ("medium_range_no_da", 3, "analysis_assim_no_da"),
    ],
)
def test_analysis_t0_cache_separate_from_forecast(
    tmp_path, monkeypatch, product, forecast_hour, analysis_product
):
    """Analysis t0 and forecast references use separate cache records."""
    import json
    from unittest.mock import MagicMock

    import fsspec
    import s3fs

    from streamflow_getter import reference_cache

    config = ForecastConfig(product=product)

    def make_reference(url):
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

    s3 = MagicMock()

    def open_reference(path, mode):
        if path == config.analysis_reference_path():
            url = config.analysis_native_url()
        else:
            assert path == config.reference_path(forecast_hour)
            url = config.native_url(forecast_hour)

        context = MagicMock()
        context.__enter__.return_value.read.return_value = (
            json.dumps(make_reference(url)).encode()
        )
        return context

    s3.open.side_effect = open_reference

    monkeypatch.setattr(
        s3fs,
        "S3FileSystem",
        lambda **kwargs: s3,
    )

    monkeypatch.setattr(
        reference_cache,
        "fetch_remote_metadata",
        lambda *args, **kwargs: {
            "reference_etag": "etag-1",
            "source_generation": "gen-1",
        },
    )

    filesystem = MagicMock()
    filesystem.get_mapper.return_value = {}

    monkeypatch.setattr(
        fsspec,
        "filesystem",
        lambda *args, **kwargs: filesystem,
    )

    def open_dataset(*args, **kwargs):
        # Use separate valid timestamps for analysis and forecast.
        hour = open_dataset.calls
        open_dataset.calls += 1

        valid = (
            "2026-04-19T00:00:00"
            if hour == 0
            else f"2026-04-19T{forecast_hour:02d}:00:00"
        )
        reference = (
            "2026-04-18T21:00:00"
            if hour == 0
            else "2026-04-19T00:00:00"
        )

        ds = xr.Dataset(
            {"streamflow": ("feature_id", [0.41])},
            coords={
                "feature_id": [3586192],
                "time": [np.datetime64(valid)],
                "reference_time": [np.datetime64(reference)],
            },
        )

        context = MagicMock()
        context.__enter__.return_value = ds
        return context

    open_dataset.calls = 0

    monkeypatch.setattr(
        xr,
        "open_zarr",
        open_dataset,
    )

    analysis_prepared = prepare_operational_reference(
        config, 0, cache_dir=tmp_path
    )
    forecast_prepared = prepare_operational_reference(
        config, forecast_hour, cache_dir=tmp_path
    )

    analysis_path = (
        tmp_path
        / config.date_folder
        / analysis_product
        / f"{config.analysis_filename()}.cache.json"
    )

    forecast_path = (
        tmp_path
        / config.date_folder
        / product
        / f"{config.filename(forecast_hour)}.cache.json"
    )

    assert reference_cache.load_cache_record(
        analysis_path, config.analysis_native_url()
    ) is not None
    assert reference_cache.load_cache_record(
        forecast_path, config.native_url(forecast_hour)
    ) is not None
    assert analysis_path != forecast_path
    assert analysis_prepared["source"]["source_product"] == analysis_product
    assert forecast_prepared["source"]["source_product"] == product
    assert open_dataset.calls == 0
    filesystem.get_mapper.assert_not_called()

    analysis = read_kerchunk_forecast(
        config, 0, [3586192], cache_dir=tmp_path
    )
    forecast = read_kerchunk_forecast(
        config, forecast_hour, [3586192], cache_dir=tmp_path
    )

    assert analysis["product"] == analysis_product
    assert forecast["product"] == product
    assert s3.open.call_count == 2


@pytest.fixture
def mock_reference_preparation(monkeypatch):
    from streamflow_getter import operational_nwm

    def prepare(config, hour, *, cache_dir):
        return {
            "source": resolve_operational_source(config, hour),
            "reference": {"full_reference": "must not be retained in summaries"},
            "reference_json_bytes": 100 + hour,
        }

    mocked = MagicMock(side_effect=prepare)
    monkeypatch.setattr(operational_nwm, "prepare_operational_reference", mocked)
    return mocked


def test_batch_validates_later_window_before_preparation(
    tmp_path, mock_reference_preparation
):
    configs = [ForecastConfig(), ForecastConfig(product="long_range_mem1")]

    with pytest.raises(ValueError, match="No available forecast leads"):
        prepare_operational_references(configs, 1, 2, cache_dir=tmp_path)

    mock_reference_preparation.assert_not_called()


@pytest.mark.parametrize(
    "overrides,error_type,message",
    [
        ({"configs": []}, ValueError, "At least one"),
        ({"configs": [ForecastConfig(), object()]}, TypeError, "ForecastConfig"),
        ({"cache_dir": None}, ValueError, "cache_dir"),
        ({"cache_dir": "   "}, ValueError, "cache_dir"),
        ({"include_t0": 1}, ValueError, "include_t0"),
    ],
    ids=["empty", "invalid-config", "no-cache", "blank-cache", "invalid-t0"],
)
def test_batch_rejects_invalid_inputs_before_preparation(
    tmp_path, mock_reference_preparation, overrides, error_type, message
):
    arguments = {
        "configs": [ForecastConfig()], "start_hour": 1, "end_hour": 1,
        "cache_dir": tmp_path, "include_t0": True,
    }
    arguments.update(overrides)

    with pytest.raises(error_type, match=message):
        prepare_operational_references(**arguments)

    mock_reference_preparation.assert_not_called()


def test_batch_deduplicates_shared_t0_in_first_seen_order(
    tmp_path, mock_reference_preparation
):
    second = ForecastConfig(product="long_range_mem2")
    first = ForecastConfig(product="long_range_mem1")
    no_da = ForecastConfig(product="medium_range_no_da")
    configs = (config for config in [second, first, no_da, second])

    summaries = prepare_operational_references(
        configs, 6, 6, cache_dir=str(tmp_path)
    )

    expected = [(second, 0), (second, 6), (first, 6), (no_da, 0), (no_da, 6)]
    assert mock_reference_preparation.call_args_list == [
        call(config, hour, cache_dir=tmp_path) for config, hour in expected
    ]
    assert summaries == [
        {
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "domain": config.domain,
            "source": resolve_operational_source(config, hour),
            "reference_json_bytes": 100 + hour,
        }
        for config, hour in expected
    ]


def test_batch_keeps_distinct_dates_and_cycles(
    tmp_path, mock_reference_preparation
):
    configs = [
        ForecastConfig(date="2026-04-19", cycle=0),
        ForecastConfig(date="2026-04-20", cycle=0),
        ForecastConfig(date="2026-04-19", cycle=6),
    ]

    summaries = prepare_operational_references(
        configs, 1, 1, cache_dir=tmp_path, include_t0=False
    )

    assert configs[0].filename(1) == configs[1].filename(1)
    assert mock_reference_preparation.call_args_list == [
        call(config, 1, cache_dir=tmp_path) for config in configs
    ]
    assert len({item["source"]["reference_path"] for item in summaries}) == 3
    assert len({item["source"]["native_url"] for item in summaries}) == 3


@pytest.mark.parametrize("include_t0", [True, False])
def test_batch_uses_each_product_schedule(
    tmp_path, mock_reference_preparation, include_t0
):
    short = ForecastConfig()
    no_da = ForecastConfig(product="medium_range_no_da")
    long_range = ForecastConfig(product="long_range_mem1")

    prepare_operational_references(
        [short, no_da, long_range], 4, 6,
        cache_dir=tmp_path, include_t0=include_t0,
    )

    expected = (
        [(short, 0), (short, 4), (short, 5), (short, 6),
         (no_da, 0), (no_da, 6), (long_range, 6)]
        if include_t0 else
        [(short, 4), (short, 5), (short, 6), (no_da, 6), (long_range, 6)]
    )
    assert mock_reference_preparation.call_args_list == [
        call(config, hour, cache_dir=tmp_path) for config, hour in expected
    ]


@pytest.mark.parametrize("error_type", [PermissionError, ValueError])
def test_batch_stops_at_original_preparation_error(
    tmp_path, mock_reference_preparation, error_type
):
    config = ForecastConfig()
    failure = error_type("Preparation failed")
    mock_reference_preparation.side_effect = [
        {
            "source": resolve_operational_source(config, 1),
            "reference": {}, "reference_json_bytes": 101,
        },
        failure,
        AssertionError("Preparation continued after failure"),
    ]

    with pytest.raises(error_type) as caught:
        prepare_operational_references(
            [config], 1, 3, cache_dir=tmp_path, include_t0=False
        )

    assert caught.value is failure
    assert mock_reference_preparation.call_args_list == [
        call(config, 1, cache_dir=tmp_path),
        call(config, 2, cache_dir=tmp_path),
    ]
