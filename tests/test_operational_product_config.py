
"""Tests for validated operational NWM product specifications."""

import pytest


from streamflow_getter.operational_nwm import (
    ForecastConfig,
    ProductSpec,
    resolve_operational_source,
)

def test_medium_range_member1_source_identity():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_mem1",
        domain="conus",
    )

    assert config.filename(1) == (
        "nwm.t00z.medium_range.channel_rt_1.f001.conus.nc"
    )

    assert config.native_url(1).endswith(
        "/nwm.20260419/medium_range_mem1/"
        "nwm.t00z.medium_range.channel_rt_1.f001.conus.nc"
    )

    assert config.reference_path(1).endswith(
        "/nwm.20260419/medium_range_mem1/"
        "nwm.t00z.medium_range.channel_rt_1.f001.conus.nc.json"
    )


@pytest.mark.parametrize("cycle", [0, 6, 12, 18])
def test_medium_range_member1_valid_cycles(cycle):
    config = ForecastConfig(
        date="2026-04-19",
        cycle=cycle,
        product="medium_range_mem1",
    )

    assert config.cycle == cycle


@pytest.mark.parametrize("cycle", [1, 3, 9, 23])
def test_medium_range_member1_invalid_cycles(cycle):
    with pytest.raises(ValueError, match="cycle"):
        ForecastConfig(
            date="2026-04-19",
            cycle=cycle,
            product="medium_range_mem1",
        )


@pytest.mark.parametrize("hour", [1, 6, 120, 240])
def test_medium_range_member1_valid_hours(hour):
    config = ForecastConfig(
        product="medium_range_mem1",
    )

    assert f"f{hour:03d}" in config.filename(hour)


@pytest.mark.parametrize("hour", [0, 241, -1])
def test_medium_range_member1_invalid_hours(hour):
    config = ForecastConfig(
        product="medium_range_mem1",
    )

    with pytest.raises(ValueError, match="hour"):
        config.filename(hour)


def test_medium_range_member1_analysis_t0():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_mem1",
    )

    assert config.analysis_filename() == (
        "nwm.t00z.analysis_assim.channel_rt.tm00.conus.nc"
    )

    assert config.analysis_native_url().endswith(
        "/nwm.20260419/analysis_assim/"
        "nwm.t00z.analysis_assim.channel_rt.tm00.conus.nc"
    )


def test_short_range_configuration_unchanged():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
    )

    assert config.product == "short_range"
    assert config.filename(1) == (
        "nwm.t00z.short_range.channel_rt.f001.conus.nc"
    )


def test_medium_range_member1_forecast_source():
    """Preserve ensemble identity in operational source resolution."""
    from streamflow_getter.operational_nwm import (
        resolve_operational_source,
    )

    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_mem1",
    )

    source = resolve_operational_source(config, 1)

    assert source["source_product"] == "medium_range_mem1"
    assert source["lead_hour"] == 1
    assert source["filename"] == (
        "nwm.t00z.medium_range.channel_rt_1.f001.conus.nc"
    )
    assert source["native_url"] == config.native_url(1)
    assert source["reference_path"] == config.reference_path(1)


def test_medium_range_member1_analysis_source():
    """Preserve analysis t0 identity and source pairing."""
    from streamflow_getter.operational_nwm import (
        resolve_operational_source,
    )

    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_mem1",
    )

    source = resolve_operational_source(config, 0)

    assert source["source_product"] == "analysis_assim"
    assert source["lead_hour"] == 0
    assert source["filename"] == (
        "nwm.t00z.analysis_assim.channel_rt.tm00.conus.nc"
    )
    assert source["native_url"] == config.analysis_native_url()
    assert source["reference_path"] == config.analysis_reference_path()


def test_medium_range_member1_series_with_t0(monkeypatch):
    """Preserve analysis t0 and medium-range forecast identity."""
    import pandas as pd

    from streamflow_getter import operational_nwm

    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_mem1",
    )

    calls = []

    def fake_fetch(config, hour, reach_ids, **kwargs):
        calls.append(hour)

        valid_time = pd.Timestamp(
            "2026-04-19T00:00:00"
        ) + pd.Timedelta(hours=hour)

        return {
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": (
                "analysis_assim"
                if hour == 0
                else config.product
            ),
            "domain": config.domain,
            "lead_hour": hour,
            "method": "kerchunk",
            "valid_time": str(valid_time),
            "reference_time": (
                "2026-04-18T21:00:00"
                if hour == 0
                else "2026-04-19T00:00:00"
            ),
            "streamflow_m3s": {3586192: 0.41},
            "reference_json_bytes": 100,
        }

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_forecast",
        fake_fetch,
    )

    frame = operational_nwm.fetch_operational_series(
        config,
        [3586192],
        1,
        2,
        include_t0=True,
    )

    assert calls == [0, 1, 2]
    assert list(frame["lead_hour"]) == [0, 1, 2]
    assert list(frame["product"]) == [
        "analysis_assim",
        "medium_range_mem1",
        "medium_range_mem1",
    ]
    assert list(frame["feature_id"]) == [3586192] * 3


def test_medium_range_member1_series_without_t0(monkeypatch):
    """Allow medium-range forecasts without analysis t0."""
    from streamflow_getter import operational_nwm

    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_mem1",
    )

    calls = []

    def fake_fetch(config, hour, reach_ids, **kwargs):
        calls.append(hour)

        return {
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": config.product,
            "domain": config.domain,
            "lead_hour": hour,
            "method": "kerchunk",
            "valid_time": f"2026-04-19T{hour:02d}:00:00",
            "reference_time": "2026-04-19T00:00:00",
            "streamflow_m3s": {3586192: 0.41},
            "reference_json_bytes": 100,
        }

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_forecast",
        fake_fetch,
    )

    frame = operational_nwm.fetch_operational_series(
        config,
        [3586192],
        1,
        2,
        include_t0=False,
    )

    assert calls == [1, 2]
    assert list(frame["lead_hour"]) == [1, 2]
    assert set(frame["product"]) == {"medium_range_mem1"}


@pytest.mark.parametrize(
    "start_hour,end_hour",
    [
        (1, 241),
        (239, 241),
        (241, 241),
    ],
)
def test_medium_range_invalid_series_range_before_fetch(
    monkeypatch, start_hour, end_hour
):
    """Reject unsupported lead hours before remote retrieval."""
    from streamflow_getter import operational_nwm

    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_mem1",
    )

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError(
            "Remote retrieval must not run for invalid lead hours"
        )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_forecast",
        unexpected_fetch,
    )

    with pytest.raises(ValueError, match="Forecast hour"):
        operational_nwm.fetch_operational_series(
            config,
            [3586192],
            start_hour,
            end_hour,
            include_t0=True,
        )


def test_medium_range_member1_cache_isolation(
    tmp_path, monkeypatch
):
    """Cache medium-range forecast and analysis t0 separately."""
    import json
    from unittest.mock import MagicMock

    import fsspec
    import numpy as np
    import s3fs
    import xarray as xr

    from streamflow_getter import reference_cache
    from streamflow_getter.operational_nwm import (
        read_kerchunk_forecast,
    )

    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_mem1",
    )

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
            assert path == config.reference_path(1)
            url = config.native_url(1)

        context = MagicMock()
        context.__enter__.return_value.read.return_value = (
            json.dumps(make_reference(url)).encode()
        )
        return context

    s3.open.side_effect = open_reference

    monkeypatch.setattr(
        s3fs, "S3FileSystem", lambda **kwargs: s3
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
        # Determine source identity from the reference.
        reference = kwargs.get("fo")
        hour = open_dataset.calls % 2
        open_dataset.calls += 1

        valid_time = np.datetime64(
            "2026-04-19T00:00:00"
        ) + np.timedelta64(hour, "h")

        reference_time = np.datetime64(
            "2026-04-18T21:00:00"
            if hour == 0
            else "2026-04-19T00:00:00"
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
                "time": [valid_time],
                "reference_time": [reference_time],
            },
        )

        context = MagicMock()
        context.__enter__.return_value = ds
        return context

    open_dataset.calls = 0

    monkeypatch.setattr(
        xr, "open_zarr", open_dataset
    )

    read_kerchunk_forecast(
        config, 0, [3586192], cache_dir=tmp_path
    )

    read_kerchunk_forecast(
        config, 1, [3586192], cache_dir=tmp_path
    )

    analysis_cache = (
        tmp_path
        / config.date_folder
        / "analysis_assim"
        / f"{config.analysis_filename()}.cache.json"
    )

    forecast_cache = (
        tmp_path
        / config.date_folder
        / "medium_range_mem1"
        / f"{config.filename(1)}.cache.json"
    )

    assert analysis_cache.exists()
    assert forecast_cache.exists()
    assert analysis_cache != forecast_cache
    assert s3.open.call_count == 2


def test_medium_range_member1_native_fallback(monkeypatch):
    """Use native fallback for a recoverable Kerchunk access failure."""
    from streamflow_getter import operational_nwm

    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_mem1",
    )

    calls = []

    def fail_kerchunk(config, hour, reach_ids):
        calls.append(("kerchunk", config.product, hour))
        raise OSError("Kerchunk reference unavailable")

    def fake_native(config, hour, reach_ids):
        calls.append(("native", config.product, hour))

        return {
            "forecast_date": config.date,
            "forecast_cycle": config.cycle,
            "product": config.product,
            "domain": config.domain,
            "lead_hour": hour,
            "method": "native_remote",
            "valid_time": "2026-04-19T01:00:00",
            "reference_time": "2026-04-19T00:00:00",
            "streamflow_m3s": {3586192: 0.41},
            "reference_json_bytes": 0,
        }

    monkeypatch.setattr(
        operational_nwm,
        "read_kerchunk_forecast",
        fail_kerchunk,
    )

    monkeypatch.setattr(
        operational_nwm,
        "read_native_forecast",
        fake_native,
    )

    result = operational_nwm.fetch_operational_forecast(
        config,
        1,
        [3586192],
    )

    assert calls == [
        ("kerchunk", "medium_range_mem1", 1),
        ("native", "medium_range_mem1", 1),
    ]

    assert result["method"] == "native_remote"
    assert result["product"] == "medium_range_mem1"
    assert result["streamflow_m3s"][3586192] == 0.41
    assert "OSError" in result["fallback_reason"]


@pytest.mark.parametrize("member", range(2, 7))
def test_additional_medium_range_member_configuration(member):
    product = f"medium_range_mem{member}"

    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product=product,
    )

    assert config.spec.directory == product
    assert config.spec.filename_product == "medium_range"
    assert config.spec.channel_family == f"channel_rt_{member}"
    assert config.spec.max_hour == 204

    assert config.filename(1) == (
        f"nwm.t00z.medium_range.channel_rt_{member}.f001.conus.nc"
    )

    assert config.filename(204) == (
        f"nwm.t00z.medium_range.channel_rt_{member}.f204.conus.nc"
    )


@pytest.mark.parametrize("member", range(2, 7))
def test_additional_medium_range_member_rejects_hour_205(member):
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product=f"medium_range_mem{member}",
    )

    with pytest.raises(ValueError, match="Forecast hour"):
        config.filename(205)


@pytest.mark.parametrize("member", range(2, 7))
@pytest.mark.parametrize("cycle", [0, 6, 12, 18])
def test_additional_medium_range_member_valid_cycles(member, cycle):
    config = ForecastConfig(
        date="2026-04-19",
        cycle=cycle,
        product=f"medium_range_mem{member}",
    )

    assert config.cycle == cycle


@pytest.mark.parametrize("member", range(2, 7))
@pytest.mark.parametrize("cycle", [1, 3, 9, 23])
def test_additional_medium_range_member_invalid_cycles(member, cycle):
    with pytest.raises(ValueError, match="cycle"):
        ForecastConfig(
            date="2026-04-19",
            cycle=cycle,
            product=f"medium_range_mem{member}",
        )


def test_medium_range_blend_configuration():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_blend",
    )

    assert config.spec.directory == "medium_range_blend"
    assert config.spec.filename_product == "medium_range_blend"
    assert config.spec.channel_family == "channel_rt"
    assert config.spec.max_hour == 240
    assert config.spec.lead_step_hours == 1

    assert config.filename(1) == (
        "nwm.t00z.medium_range_blend.channel_rt.f001.conus.nc"
    )

    assert config.filename(240) == (
        "nwm.t00z.medium_range_blend.channel_rt.f240.conus.nc"
    )


@pytest.mark.parametrize("cycle", [0, 6, 12, 18])
def test_medium_range_blend_valid_cycles(cycle):
    config = ForecastConfig(
        date="2026-04-19",
        cycle=cycle,
        product="medium_range_blend",
    )

    assert config.cycle == cycle


@pytest.mark.parametrize("cycle", [1, 3, 9, 23])
def test_medium_range_blend_invalid_cycles(cycle):
    with pytest.raises(ValueError, match="cycle"):
        ForecastConfig(
            date="2026-04-19",
            cycle=cycle,
            product="medium_range_blend",
        )


def test_medium_range_blend_rejects_hour_241():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_blend",
    )

    with pytest.raises(ValueError, match="Forecast hour"):
        config.filename(241)


def test_medium_range_blend_source_paths():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_blend",
    )

    filename = (
        "nwm.t00z.medium_range_blend.channel_rt.f001.conus.nc"
    )

    assert config.native_url(1).endswith(
        f"/nwm.20260419/medium_range_blend/{filename}"
    )

    assert config.reference_path(1).endswith(
        f"/nwm.20260419/medium_range_blend/{filename}.json"
    )


def test_medium_range_no_da_configuration():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_no_da",
    )

    assert config.spec.directory == "medium_range_no_da"
    assert config.spec.filename_product == "medium_range_no_da"
    assert config.spec.channel_family == "channel_rt"
    assert config.spec.max_hour == 240
    assert config.spec.lead_step_hours == 3
    assert config.spec.analysis_product == "analysis_assim_no_da"

    assert config.forecast_hours(1, 12) == [3, 6, 9, 12]
    assert config.forecast_hours(4, 12) == [6, 9, 12]

    assert config.filename(3) == (
        "nwm.t00z.medium_range_no_da.channel_rt.f003.conus.nc"
    )


@pytest.mark.parametrize("cycle", [0, 6, 12, 18])
def test_medium_range_no_da_valid_cycles(cycle):
    config = ForecastConfig(
        date="2026-04-19",
        cycle=cycle,
        product="medium_range_no_da",
    )

    assert config.cycle == cycle


@pytest.mark.parametrize("cycle", [1, 3, 9, 23])
def test_medium_range_no_da_invalid_cycles(cycle):
    with pytest.raises(ValueError, match="cycle"):
        ForecastConfig(
            date="2026-04-19",
            cycle=cycle,
            product="medium_range_no_da",
        )


@pytest.mark.parametrize("hour", [1, 2, 4, 5, 241])
def test_medium_range_no_da_invalid_hours(hour):
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_no_da",
    )

    with pytest.raises(ValueError, match="Forecast hour"):
        config.filename(hour)


def test_medium_range_no_da_analysis_source():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_no_da",
    )

    source = resolve_operational_source(config, 0)

    assert source["source_product"] == "analysis_assim_no_da"
    assert source["filename"] == (
        "nwm.t00z.analysis_assim_no_da.channel_rt.tm00.conus.nc"
    )
    assert "/analysis_assim_no_da/" in source["native_url"]
    assert "/analysis_assim_no_da/" in source["reference_path"]


def test_medium_range_no_da_forecast_source():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="medium_range_no_da",
    )

    source = resolve_operational_source(config, 3)

    assert source["source_product"] == "medium_range_no_da"
    assert source["filename"] == (
        "nwm.t00z.medium_range_no_da.channel_rt.f003.conus.nc"
    )


def test_long_range_mem1_configuration():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="long_range_mem1",
    )

    assert config.spec.directory == "long_range_mem1"
    assert config.spec.filename_product == "long_range"
    assert config.spec.channel_family == "channel_rt_1"
    assert config.spec.max_hour == 720
    assert config.spec.lead_step_hours == 6

    assert config.forecast_hours(1, 24) == [6, 12, 18, 24]
    assert config.forecast_hours(7, 24) == [12, 18, 24]

    assert config.filename(6) == (
        "nwm.t00z.long_range.channel_rt_1.f006.conus.nc"
    )
    assert config.filename(720) == (
        "nwm.t00z.long_range.channel_rt_1.f720.conus.nc"
    )


@pytest.mark.parametrize("cycle", [0, 6, 12, 18])
def test_long_range_mem1_valid_cycles(cycle):
    config = ForecastConfig(
        date="2026-04-19",
        cycle=cycle,
        product="long_range_mem1",
    )

    assert config.cycle == cycle


@pytest.mark.parametrize("cycle", [1, 3, 9, 23])
def test_long_range_mem1_invalid_cycles(cycle):
    with pytest.raises(ValueError, match="cycle"):
        ForecastConfig(
            date="2026-04-19",
            cycle=cycle,
            product="long_range_mem1",
        )


@pytest.mark.parametrize("hour", [1, 3, 7, 11, 721])
def test_long_range_mem1_invalid_hours(hour):
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="long_range_mem1",
    )

    with pytest.raises(ValueError, match="Forecast hour"):
        config.filename(hour)


def test_long_range_mem1_source_paths():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="long_range_mem1",
    )

    source = resolve_operational_source(config, 6)

    assert source["source_product"] == "long_range_mem1"
    assert source["filename"] == (
        "nwm.t00z.long_range.channel_rt_1.f006.conus.nc"
    )
    assert "/long_range_mem1/" in source["native_url"]
    assert "/long_range_mem1/" in source["reference_path"]


def test_long_range_mem1_analysis_source():
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product="long_range_mem1",
    )

    source = resolve_operational_source(config, 0)

    assert source["source_product"] == "analysis_assim"
    assert source["filename"] == (
        "nwm.t00z.analysis_assim.channel_rt.tm00.conus.nc"
    )


@pytest.mark.parametrize("member", [2, 3, 4])
def test_long_range_ensemble_configuration(member):
    product = f"long_range_mem{member}"

    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product=product,
    )

    assert config.spec.directory == product
    assert config.spec.filename_product == "long_range"
    assert config.spec.channel_family == f"channel_rt_{member}"
    assert config.spec.max_hour == 720
    assert config.spec.lead_step_hours == 6
    assert config.spec.analysis_product == "analysis_assim"

    assert config.forecast_hours(1, 24) == [6, 12, 18, 24]
    assert config.forecast_hours(7, 24) == [12, 18, 24]

    assert config.filename(6) == (
        f"nwm.t00z.long_range.channel_rt_{member}.f006.conus.nc"
    )

    assert config.filename(720) == (
        f"nwm.t00z.long_range.channel_rt_{member}.f720.conus.nc"
    )


@pytest.mark.parametrize("member", [2, 3, 4])
@pytest.mark.parametrize("cycle", [0, 6, 12, 18])
def test_long_range_ensemble_valid_cycles(member, cycle):
    config = ForecastConfig(
        date="2026-04-19",
        cycle=cycle,
        product=f"long_range_mem{member}",
    )

    assert config.cycle == cycle


@pytest.mark.parametrize("member", [2, 3, 4])
@pytest.mark.parametrize("cycle", [1, 3, 9, 23])
def test_long_range_ensemble_invalid_cycles(member, cycle):
    with pytest.raises(ValueError, match="cycle"):
        ForecastConfig(
            date="2026-04-19",
            cycle=cycle,
            product=f"long_range_mem{member}",
        )


@pytest.mark.parametrize("member", [2, 3, 4])
@pytest.mark.parametrize("hour", [1, 3, 7, 11, 721])
def test_long_range_ensemble_invalid_hours(member, hour):
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product=f"long_range_mem{member}",
    )

    with pytest.raises(ValueError, match="Forecast hour"):
        config.filename(hour)


@pytest.mark.parametrize("member", [2, 3, 4])
def test_long_range_ensemble_forecast_source(member):
    product = f"long_range_mem{member}"

    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product=product,
    )

    source = resolve_operational_source(config, 6)

    assert source["source_product"] == product
    assert source["filename"] == (
        f"nwm.t00z.long_range.channel_rt_{member}.f006.conus.nc"
    )
    assert f"/{product}/" in source["native_url"]
    assert f"/{product}/" in source["reference_path"]


@pytest.mark.parametrize("member", [2, 3, 4])
def test_long_range_ensemble_analysis_source(member):
    config = ForecastConfig(
        date="2026-04-19",
        cycle=0,
        product=f"long_range_mem{member}",
    )

    source = resolve_operational_source(config, 0)

    assert source["source_product"] == "analysis_assim"
    assert source["filename"] == (
        "nwm.t00z.analysis_assim.channel_rt.tm00.conus.nc"
    )

@pytest.mark.parametrize("member", range(1, 7))
@pytest.mark.parametrize(
    "date,cycle,expected_step",
    [
        ("2021-04-20", 0, 3),
        ("2021-04-20", 6, 3),
        ("2021-04-20", 12, 1),
        ("2021-04-20", 18, 1),
        ("2021-04-21", 0, 1),
        ("2026-04-19", 0, 1),
    ],
)
def test_historical_medium_range_lead_step(
    member, date, cycle, expected_step
):
    config = ForecastConfig(
        date=date,
        cycle=cycle,
        product=f"medium_range_mem{member}",
    )

    assert config.lead_step_hours == expected_step

    expected_hours = list(range(expected_step, 13, expected_step))
    assert config.forecast_hours(1, 12) == expected_hours


@pytest.mark.parametrize("member", range(1, 7))
@pytest.mark.parametrize("cycle", [0, 6])
def test_historical_medium_range_rejects_unavailable_lead(
    member, cycle
):
    config = ForecastConfig(
        date="2021-04-20",
        cycle=cycle,
        product=f"medium_range_mem{member}",
    )

    with pytest.raises(ValueError, match="multiple of 3"):
        config.filename(1)

    assert ".f003." in config.filename(3)


@pytest.mark.parametrize("member", range(1, 7))
def test_historical_medium_range_full_horizon(member):
    config = ForecastConfig(
        date="2021-04-20",
        cycle=6,
        product=f"medium_range_mem{member}",
    )

    max_hour = 240 if member == 1 else 204
    hours = config.forecast_hours(1, max_hour)

    assert hours[0] == 3
    assert hours[-1] == max_hour
    assert len(hours) == max_hour // 3


def test_other_products_keep_existing_lead_steps():
    cases = [
        ("short_range", 1),
        ("medium_range_no_da", 3),
        ("long_range_mem1", 6),
    ]

    for product, expected_step in cases:
        config = ForecastConfig(
            date="2021-04-20",
            cycle=0,
            product=product,
        )

        assert config.lead_step_hours == expected_step