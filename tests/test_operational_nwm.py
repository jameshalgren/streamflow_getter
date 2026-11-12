"""Tests for operational NWM forecast configuration and extraction."""
import numpy as np
import pytest
import xarray as xr

from streamflow_getter.operational_nwm import (
    ForecastConfig,
    extract_streamflow,
    resolve_operational_source,
)

def test_resolve_analysis_t0_source():
    config = ForecastConfig(date="2026-04-19", cycle=0)

    source = resolve_operational_source(config, 0)

    assert source["source_product"] == "analysis_assim"
    assert source["lead_hour"] == 0
    assert source["filename"] == (
        "nwm.t00z.analysis_assim.channel_rt.tm00.conus.nc"
    )
    assert source["native_url"] == config.analysis_native_url()
    assert source["reference_path"] == config.analysis_reference_path()


def test_resolve_forecast_source():
    config = ForecastConfig(date="2026-04-19", cycle=0)

    source = resolve_operational_source(config, 1)

    assert source["source_product"] == "short_range"
    assert source["lead_hour"] == 1
    assert source["filename"] == config.filename(1)
    assert source["native_url"] == config.native_url(1)
    assert source["reference_path"] == config.reference_path(1)


@pytest.mark.parametrize("hour", [-1, 1.5, True])
def test_resolve_invalid_lead_hour(hour):
    with pytest.raises(ValueError):
        resolve_operational_source(ForecastConfig(), hour)


def test_forecast_source_identity():
    config = ForecastConfig()
    assert config.date_folder == "nwm.20260419"
    assert config.cycle_name == "t00z"
    assert config.filename(1) == "nwm.t00z.short_range.channel_rt.f001.conus.nc"
    assert config.native_url(1).endswith(
        "/nwm.20260419/short_range/nwm.t00z.short_range.channel_rt.f001.conus.nc"
    )
    assert config.reference_path(1).endswith(
        "/nwm.20260419/short_range/nwm.t00z.short_range.channel_rt.f001.conus.nc.json"
    )


def test_forecast_timestamps():
    ForecastConfig(date="2026-04-20", cycle=12).validate_timestamps(
        1, "2026-04-20T13:00:00", "2026-04-20T12:00:00"
    )


def test_wrong_forecast_reference_time():
    with pytest.raises(ValueError, match="reference time"):
        ForecastConfig(date="2026-04-20", cycle=12).validate_timestamps(
            1, "2026-04-19T01:00:00", "2026-04-19T00:00:00"
        )


def test_wrong_forecast_valid_time():
    with pytest.raises(ValueError, match="valid time"):
        ForecastConfig(date="2026-04-20", cycle=12).validate_timestamps(
            1, "2026-04-20T14:00:00", "2026-04-20T12:00:00"
        )


@pytest.mark.parametrize("kwargs", [
    {"date": "2026-02-30"}, {"cycle": -1}, {"cycle": 24},
    {"cycle": True}, {"product": "medium_range"}, {"domain": "alaska"},
])
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        ForecastConfig(**kwargs)


@pytest.mark.parametrize("hour", [-1, 0, 1.5, True])
def test_invalid_forecast_hour(hour):
    with pytest.raises(ValueError):
        ForecastConfig().filename(hour)


@pytest.mark.parametrize(
    "forecast_date, cycle, hour, filename",
    [
        (
            "2026-04-19",
            0,
            1,
            "nwm.t00z.short_range.channel_rt.f001.conus.nc",
        ),
        (
            "2026-04-19",
            0,
            6,
            "nwm.t00z.short_range.channel_rt.f006.conus.nc",
        ),
        (
            "2026-04-19",
            12,
            18,
            "nwm.t12z.short_range.channel_rt.f018.conus.nc",
        ),
        (
            "2026-04-20",
            6,
            3,
            "nwm.t06z.short_range.channel_rt.f003.conus.nc",
        ),
    ],
)
def test_forecast_config_source_paths(
    forecast_date, cycle, hour, filename
):
    config = ForecastConfig(date=forecast_date, cycle=cycle)

    date_folder = forecast_date.replace("-", "")

    assert config.filename(hour) == filename

    assert config.native_url(hour) == (
        "https://storage.googleapis.com/national-water-model/"
        f"nwm.{date_folder}/short_range/{filename}"
    )

    assert config.reference_path(hour) == (
        "ciroh-nwm-zarr-copy/national-water-model/"
        f"nwm.{date_folder}/short_range/{filename}.json"
    )


@pytest.fixture
def operational_dataset():
    return xr.Dataset(
        {"streamflow": ("feature_id", [7.08, 0.41, 0.0])},
        coords={"feature_id": [1122645, 3586192, 7144704]},
    )


def test_extract_streamflow_multiple_reaches(operational_dataset):
    result = extract_streamflow(operational_dataset, [3586192, 1122645])
    assert list(result) == [3586192, 1122645]
    assert result == {3586192: 0.41, 1122645: 7.08}


def test_extract_streamflow_missing_reach(operational_dataset):
    with pytest.raises(ValueError, match="Missing reaches"):
        extract_streamflow(operational_dataset, [999999])


def test_extract_streamflow_duplicate_request(operational_dataset):
    with pytest.raises(ValueError, match="Duplicate"):
        extract_streamflow(operational_dataset, [3586192, 3586192])


def test_extract_streamflow_nonfinite(operational_dataset):
    operational_dataset["streamflow"].values[1] = np.nan
    with pytest.raises(ValueError, match="Non-finite"):
        extract_streamflow(operational_dataset, [3586192])


def test_extract_streamflow_duplicate_dataset_id(operational_dataset):
    invalid = operational_dataset.assign_coords(feature_id=[3586192, 3586192, 7144704])
    with pytest.raises(ValueError, match="Duplicate feature ID"):
        extract_streamflow(invalid, [3586192])


def test_extract_streamflow_invalid_request(operational_dataset):
    with pytest.raises(ValueError, match="positive integers"):
        extract_streamflow(operational_dataset, [3586192.5])


def test_extract_streamflow_invalid_shape():
    ds = xr.Dataset(
        {"streamflow": (("time", "feature_id"), [[7.08, 0.41, 0.0]])},
        coords={"time": [0], "feature_id": [1122645, 3586192, 7144704]},
    )
    with pytest.raises(ValueError, match="shape"):
        extract_streamflow(ds, [3586192])



def test_extract_streamflow_preserves_values_and_order():
    """Verify exact streamflow values in the requested reach order."""
    ds = xr.Dataset(
        {
            "streamflow": (
                "feature_id",
                [7.08, 0.41, 0.0, 16062.71, 0.01],
            ),
        },
        coords={
            "feature_id": [
                1122645,
                3586192,
                7144704,
                14191043,
                23610484,
            ],
        },
    )

    requested = [14191043, 1122645, 3586192]
    expected = [16062.71, 7.08, 0.41]

    result = extract_streamflow(ds, requested)

    assert list(result) == requested

    np.testing.assert_allclose(
        list(result.values()),
        expected,
        rtol=0,
        atol=0,
    )



def test_analysis_t0_source_identity():
    config = ForecastConfig(date="2026-04-19", cycle=0)

    filename = (
        "nwm.t00z.analysis_assim.channel_rt.tm00.conus.nc"
    )

    assert config.analysis_filename() == filename

    assert config.analysis_native_url() == (
        "https://storage.googleapis.com/national-water-model/"
        f"nwm.20260419/analysis_assim/{filename}"
    )

    assert config.analysis_reference_path() == (
        "ciroh-nwm-zarr-copy/national-water-model/"
        f"nwm.20260419/analysis_assim/{filename}.json"
    )


@pytest.mark.parametrize("cycle", [0, 1, 6, 12, 18, 23])
def test_analysis_t0_valid_time(cycle):
    config = ForecastConfig(date="2026-04-19", cycle=cycle)

    config.validate_analysis_timestamps(
        f"2026-04-19T{cycle:02d}:00:00",
        np.datetime64(
            f"2026-04-19T{cycle:02d}:00:00"
        ) - np.timedelta64(3, "h"),
    )


def test_analysis_t0_preserves_reference_time():
    config = ForecastConfig()

    # The source reference time is not required to equal
    # the requested forecast cycle time.
    config.validate_analysis_timestamps(
        "2026-04-19T00:00:00",
        "2026-04-18T21:00:00",
    )


def test_analysis_t0_rejects_wrong_valid_time():
    config = ForecastConfig()

    with pytest.raises(ValueError, match="analysis t0 valid time"):
        config.validate_analysis_timestamps(
            "2026-04-19T01:00:00",
            "2026-04-18T21:00:00",
        )


def test_analysis_t0_rejects_missing_reference_time():
    config = ForecastConfig()

    with pytest.raises(ValueError, match="reference time"):
        config.validate_analysis_timestamps(
            "2026-04-19T00:00:00",
            np.datetime64("NaT", "s"),
        )

@pytest.mark.parametrize("dtype", [np.int32, np.int64])
def test_extract_streamflow_numpy_integer_feature_ids(dtype):
    """Historical NWM integer feature IDs must remain valid."""
    ds = xr.Dataset(
        {
            "streamflow": (
                "feature_id",
                [0.41, 1.25],
            ),
        },
        coords={
            "feature_id": np.array(
                [3586192, 1122645],
                dtype=dtype,
            ),
        },
    )

    result = extract_streamflow(ds, [3586192])

    assert result == {3586192: 0.41}