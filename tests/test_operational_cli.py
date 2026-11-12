
"""Offline tests for the operational NWM CLI."""

import pandas as pd
import pytest

from streamflow_getter.cli import build_parser, main
from streamflow_getter import operational_nwm, output


@pytest.fixture
def mock_operational(monkeypatch):
    """Mock realistic retrieval and manifest publication without network."""
    from datetime import date, datetime, timedelta

    calls = {}

    columns = [
        "forecast_date",
        "forecast_cycle",
        "product",
        "domain",
        "lead_hour",
        "feature_id",
        "valid_time",
        "reference_time",
        "streamflow_m3s",
        "method",
    ]

    def make_frame(
        config,
        reaches,
        start_hour,
        end_hour,
        *,
        include_t0,
    ):
        """Build rows consistent with the requested ForecastConfig."""
        cycle_time = datetime.combine(
            date.fromisoformat(
                config.date
            ),
            datetime.min.time(),
        ).replace(
            hour=config.cycle
        )

        rows = []

        if include_t0:
            # Keep source provenance realistic. Analysis reference time
            # is allowed to differ from analysis t0 valid time.
            analysis_reference_time = (
                cycle_time
                - timedelta(hours=3)
            )

            for reach in reaches:
                rows.append({
                    "forecast_date": config.date,
                    "forecast_cycle": config.cycle,
                    "product": config.spec.analysis_product,
                    "domain": config.domain,
                    "lead_hour": 0,
                    "feature_id": reach,
                    "valid_time": (
                        cycle_time.isoformat()
                    ),
                    "reference_time": (
                        analysis_reference_time.isoformat()
                    ),
                    "streamflow_m3s": 0.41,
                    "method": "kerchunk",
                })

        hours = config.forecast_hours(
            start_hour,
            end_hour,
        )

        for hour in hours:
            valid_time = (
                cycle_time
                + timedelta(hours=hour)
            )

            for reach in reaches:
                rows.append({
                    "forecast_date": config.date,
                    "forecast_cycle": config.cycle,
                    "product": config.product,
                    "domain": config.domain,
                    "lead_hour": hour,
                    "feature_id": reach,
                    "valid_time": (
                        valid_time.isoformat()
                    ),
                    "reference_time": (
                        cycle_time.isoformat()
                    ),
                    "streamflow_m3s": 0.41,
                    "method": "kerchunk",
                })

        return pd.DataFrame(
            rows,
            columns=columns,
        )

    # Preserve the expected default frame used by the original
    # test_operational_cli_defaults assertion.
    default_config = (
        operational_nwm.ForecastConfig()
    )

    frame = make_frame(
        default_config,
        [3586192],
        1,
        18,
        include_t0=True,
    )

    def fake_fetch(
        config,
        reaches,
        start_hour,
        end_hour,
        **kwargs,
    ):
        calls["config"] = config
        calls["reaches"] = reaches
        calls["start_hour"] = start_hour
        calls["end_hour"] = end_hour
        calls["fetch_kwargs"] = kwargs

        include_t0 = kwargs.get(
            "include_t0",
            True,
        )

        result = make_frame(
            config,
            reaches,
            start_hour,
            end_hour,
            include_t0=include_t0,
        )

        calls["returned_frame"] = result

        return result

    def fake_write(
        data,
        path,
        manifest,
        **kwargs,
    ):
        calls["written_frame"] = data
        calls["manifest"] = manifest
        calls["output_path"] = path
        calls["write_kwargs"] = kwargs

        manifest_path = kwargs.get(
            "manifest_path"
        )

        if manifest_path is None:
            manifest_path = (
                output.manifest_path_for(
                    path
                )
            )

        return (
            path,
            manifest_path,
        )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fake_fetch,
    )

    monkeypatch.setattr(
        output,
        "write_timeseries_with_manifest",
        fake_write,
    )

    return calls, frame


def test_operational_cli_defaults(mock_operational):
    calls, frame = mock_operational

    result = main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--out", "forecast.csv",
    ])

    assert result == 0
    assert calls["config"].date == "2026-04-19"
    assert calls["config"].cycle == 0
    assert calls["reaches"] == [3586192]
    assert calls["start_hour"] == 1
    assert calls["end_hour"] == 18
    assert calls["fetch_kwargs"]["include_t0"] is True
    pd.testing.assert_frame_equal(
        calls["written_frame"],
        frame,
    )
    assert calls["output_path"] == "forecast.csv"


def test_operational_cli_no_t0(mock_operational):
    calls, _ = mock_operational

    main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--no-t0",
        "--out", "forecast.csv",
    ])

    assert calls["fetch_kwargs"]["include_t0"] is False


def test_operational_cli_parquet_and_cache(mock_operational):
    calls, _ = mock_operational

    main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--cycle", "12",
        "--reach", "3586192",
        "--reach", "1122645",
        "--start-hour", "2",
        "--end-hour", "6",
        "--cache-dir", "/tmp/nwm-cache",
        "--format", "parquet",
        "--out", "forecast.parquet",
    ])

    assert calls["config"].cycle == 12
    assert calls["reaches"] == [3586192, 1122645]
    assert calls["start_hour"] == 2
    assert calls["end_hour"] == 6
    assert calls["fetch_kwargs"]["cache_dir"] == "/tmp/nwm-cache"
    assert calls["write_kwargs"]["output_format"] == "parquet"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--reach", "3586192", "--out", "forecast.csv"],
        ["--date", "2026-04-19", "--reach", "3586192"],
        [
            "--date", "2026-04-19",
            "--reach", "3586192",
            "--format", "json",
            "--out", "forecast.json",
        ],
    ],
)
def test_operational_cli_rejects_invalid_arguments(arguments):
    parser = build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["nwm-operational", *arguments])

    assert exc.value.code == 2


def test_existing_retrospective_parser():
    parser = build_parser()

    args = parser.parse_args([
        "nwm",
        "--gage", "01646500",
        "--version", "2.1",
        "--start", "2015-05-23",
        "--end", "2015-06-24",
        "--out", "flow.csv",
    ])

    assert args.source == "nwm"
    assert args.gage == ["01646500"]
    assert args.nwm_version == "2.1"
    assert args.out == "flow.csv"



@pytest.mark.parametrize("extension", ["csv", "parquet"])
def test_operational_cli_writes_real_output(
    tmp_path, monkeypatch, extension
):
    """Verify CLI integration with the actual CSV/Parquet writer."""
    from streamflow_getter import operational_nwm

    frame = pd.DataFrame({
        "forecast_date": ["2026-04-19", "2026-04-19"],
        "forecast_cycle": [0, 0],
        "product": ["analysis_assim", "short_range"],
        "domain": ["conus", "conus"],
        "lead_hour": [0, 1],
        "feature_id": [3586192, 3586192],
        "valid_time": [
            "2026-04-19T00:00:00",
            "2026-04-19T01:00:00",
        ],
        "reference_time": [
            "2026-04-18T21:00:00",
            "2026-04-19T00:00:00",
        ],
        "streamflow_m3s": [0.41, 0.42],
        "method": ["kerchunk", "kerchunk"],
    })

    def fake_fetch(config, reaches, start_hour, end_hour, **kwargs):
        assert reaches == [3586192]
        assert kwargs["include_t0"] is True
        return frame

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        fake_fetch,
    )

    destination = tmp_path / f"forecast.{extension}"

    result = main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "1",
        "--out", str(destination),
    ])

    assert result == 0
    assert destination.exists()

    if extension == "csv":
        restored = pd.read_csv(destination)
    else:
        restored = pd.read_parquet(destination)

    assert len(restored) == 2
    assert restored["lead_hour"].tolist() == [0, 1]
    assert restored["product"].tolist() == [
        "analysis_assim",
        "short_range",
    ]
    assert restored["reference_time"].tolist() == [
        "2026-04-18T21:00:00",
        "2026-04-19T00:00:00",
    ]



def test_retrospective_cli_execution(tmp_path, monkeypatch):
    """Preserve existing retrospective retrieval and CSV output."""
    from streamflow_getter import nwm

    calls = {}

    class FakeDataset:
        pass

    dataset = FakeDataset()

    def fake_open(version):
        calls["version"] = version
        return dataset

    def fake_gages(gages, ds):
        assert ds is dataset
        assert gages == ["01646500"]
        return {"01646500": 1122645}

    def fake_fetch(reaches, start, end, variable, *, ds):
        assert ds is dataset
        calls["reaches"] = reaches
        calls["start"] = start
        calls["end"] = end
        calls["variable"] = variable

        return pd.DataFrame({
            "time": ["2015-05-23T00:00:00"],
            "feature_id": [1122645],
            "streamflow": [7.08],
        })

    monkeypatch.setattr(nwm, "open_chrtout", fake_open)
    monkeypatch.setattr(nwm, "gages_to_reaches", fake_gages)
    monkeypatch.setattr(nwm, "fetch", fake_fetch)

    destination = tmp_path / "retrospective.csv"

    result = main([
        "nwm",
        "--gage", "01646500",
        "--version", "2.1",
        "--start", "2015-05-23",
        "--end", "2015-06-24",
        "--out", str(destination),
    ])

    assert result == 0
    assert calls == {
        "version": "2.1",
        "reaches": [1122645],
        "start": "2015-05-23",
        "end": "2015-06-24",
        "variable": "streamflow",
    }

    restored = pd.read_csv(destination)

    assert restored["feature_id"].tolist() == [1122645]
    assert restored["streamflow"].tolist() == [7.08]



@pytest.mark.parametrize(
    "filename,output_format",
    [
        ("forecast.txt", None),
        ("forecast.csv", "parquet"),
        ("forecast.parquet", "csv"),
    ],
)
def test_cli_rejects_invalid_output_before_fetch(
    tmp_path, monkeypatch, filename, output_format
):
    """Invalid output configuration must not trigger retrieval."""
    from streamflow_getter import operational_nwm

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    destination = tmp_path / filename

    arguments = [
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--out", str(destination),
    ]

    if output_format is not None:
        arguments.extend(["--format", output_format])

    with pytest.raises(ValueError):
        main(arguments)

    assert not destination.exists()


def test_cli_rejects_existing_output_before_fetch(
    tmp_path, monkeypatch
):
    """Existing output must be preserved without retrieval."""
    from streamflow_getter import operational_nwm

    destination = tmp_path / "forecast.csv"
    destination.write_text("existing-data")

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(FileExistsError):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--reach", "3586192",
            "--out", str(destination),
        ])

    assert destination.read_text() == "existing-data"



@pytest.mark.parametrize(
    "date,cycle",
    [
        ("2026-02-30", "0"),
        ("2026/04/19", "0"),
        ("2026-04-19", "24"),
        ("2026-04-19", "-1"),
    ],
)
def test_cli_rejects_invalid_configuration_before_fetch(
    monkeypatch, tmp_path, date, cycle
):
    from streamflow_getter import operational_nwm

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(ValueError):
        main([
            "nwm-operational",
            "--date", date,
            "--cycle", cycle,
            "--reach", "3586192",
            "--out", str(tmp_path / "forecast.csv"),
        ])


@pytest.mark.parametrize(
    "start_hour,end_hour",
    [
        ("0", "1"),
        ("2", "1"),
        ("-1", "2"),
    ],
)
def test_cli_rejects_invalid_hours_before_fetch(
    monkeypatch, tmp_path, start_hour, end_hour
):
    from streamflow_getter import operational_nwm

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(ValueError):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--reach", "3586192",
            "--start-hour", start_hour,
            "--end-hour", end_hour,
            "--out", str(tmp_path / "forecast.csv"),
        ])




def test_operational_cli_requires_reach_selection(tmp_path):
    """Reject requests without any reach-selection method."""
    with pytest.raises(
        ValueError,
        match=r"Provide at least one --reach, --gage, --point, --bbox, or --polygon",
    ):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--out", str(tmp_path / "forecast.csv"),
        ])



def test_operational_cli_gage_resolution(
    tmp_path, monkeypatch, mock_operational
):
    """Resolve a leading-zero USGS gage before retrieval."""
    from streamflow_getter import reach_resolution

    calls, _ = mock_operational

    routelink = tmp_path / "RouteLink.nc"
    routelink.touch()

    def fake_load(path):
        assert str(path) == str(routelink)
        return {"08165500": 3586192}

    monkeypatch.setattr(
        reach_resolution,
        "load_gage_index",
        fake_load,
    )

    result = main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--gage", "08165500",
        "--routelink", str(routelink),
        "--out", str(tmp_path / "forecast.csv"),
    ])

    assert result == 0
    assert calls["reaches"] == [3586192]


def test_operational_cli_mixed_reaches(
    tmp_path, monkeypatch, mock_operational
):
    """Combine direct reaches and resolved gages."""
    from streamflow_getter import reach_resolution

    calls, _ = mock_operational

    monkeypatch.setattr(
        reach_resolution,
        "load_gage_index",
        lambda path: {"08165500": 3586192},
    )

    main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "1122645",
        "--gage", "08165500",
        "--routelink", str(tmp_path / "RouteLink.nc"),
        "--out", str(tmp_path / "forecast.csv"),
    ])

    assert calls["reaches"] == [1122645, 3586192]


def test_operational_cli_rejects_duplicate_reach(
    tmp_path, monkeypatch
):
    """Reject duplicate IDs from direct and gage selections."""
    from streamflow_getter import reach_resolution
    from streamflow_getter import operational_nwm

    monkeypatch.setattr(
        reach_resolution,
        "load_gage_index",
        lambda path: {"08165500": 3586192},
    )

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(ValueError, match="Duplicate"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--reach", "3586192",
            "--gage", "08165500",
            "--routelink", str(tmp_path / "RouteLink.nc"),
            "--out", str(tmp_path / "forecast.csv"),
        ])


@pytest.mark.parametrize(
    "arguments,expected_error",
    [
        (
            ["--gage", "08165500"],
            "--routelink is required",
        ),
        (
            ["--reach", "3586192",
             "--routelink", "RouteLink.nc"],
            "--routelink requires",
        ),
    ],
)
def test_operational_cli_invalid_gage_arguments(
    tmp_path, arguments, expected_error
):
    """Reject incomplete RouteLink argument combinations."""
    with pytest.raises(ValueError, match=expected_error):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            *arguments,
            "--out", str(tmp_path / "forecast.csv"),
        ])


def test_operational_cli_unknown_gage_before_fetch(
    tmp_path, monkeypatch
):
    """Reject unknown gages without requesting NWM data."""
    from streamflow_getter import operational_nwm, reach_resolution

    monkeypatch.setattr(
        reach_resolution,
        "load_gage_index",
        lambda path: {"08165500": 3586192},
    )

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("NWM retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(ValueError, match="not found"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--gage", "99999999",
            "--routelink", str(tmp_path / "RouteLink.nc"),
            "--out", str(tmp_path / "forecast.csv"),
        ])


def test_operational_cli_missing_routelink_before_fetch(
    tmp_path, monkeypatch
):
    """Reject missing RouteLink files before NWM retrieval."""
    from streamflow_getter import operational_nwm

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("NWM retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(FileNotFoundError, match="not found"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--gage", "08165500",
            "--routelink", str(tmp_path / "missing.nc"),
            "--out", str(tmp_path / "forecast.csv"),
        ])

def test_operational_cli_point_parser():
    parser = build_parser()

    args = parser.parse_args([
        "nwm-operational",
        "--date", "2026-04-19",
        "--point", "-99.321712", "30.069931",
        "--hydrofabric", "NWM_v3_hydrofabric.gdb",
        "--out", "forecast.csv",
    ])

    assert args.point == [-99.321712, 30.069931]
    assert args.hydrofabric == "NWM_v3_hydrofabric.gdb"
    assert args.max_distance_m == 500.0


def test_operational_cli_point_custom_distance():
    parser = build_parser()

    args = parser.parse_args([
        "nwm-operational",
        "--date", "2026-04-19",
        "--point", "-99.321712", "30.069931",
        "--hydrofabric", "NWM_v3_hydrofabric.gdb",
        "--max-distance-m", "1000",
        "--out", "forecast.csv",
    ])

    assert args.max_distance_m == 1000.0



def test_operational_cli_point_resolution(
    tmp_path, monkeypatch, mock_operational
):
    """Resolve a geographic point before operational retrieval."""
    from streamflow_getter import spatial_resolution

    calls, _ = mock_operational

    monkeypatch.setattr(
        spatial_resolution,
        "load_nearby_reaches",
        lambda *args, **kwargs: "mocked-geometries",
    )

    monkeypatch.setattr(
        spatial_resolution,
        "nearest_reaches",
        lambda *args, **kwargs: [
            {"feature_id": 3586192, "distance_m": 98.34}
        ],
    )

    result = main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--point", "-99.321712", "30.069931",
        "--hydrofabric", "test.gdb",
        "--out", str(tmp_path / "forecast.csv"),
    ])

    assert result == 0
    assert calls["reaches"] == [3586192]


def test_operational_cli_point_requires_hydrofabric(tmp_path):
    """Reject geographic selection without a hydrofabric."""
    with pytest.raises(ValueError, match="--hydrofabric is required"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--point", "-99.321712", "30.069931",
            "--out", str(tmp_path / "forecast.csv"),
        ])


def test_operational_cli_point_no_candidates(
    tmp_path, monkeypatch
):
    """Reject unmatched points before remote retrieval."""
    from streamflow_getter import spatial_resolution

    monkeypatch.setattr(
        spatial_resolution,
        "load_nearby_reaches",
        lambda *args, **kwargs: "mocked-geometries",
    )

    monkeypatch.setattr(
        spatial_resolution,
        "nearest_reaches",
        lambda *args, **kwargs: [],
    )

    with pytest.raises(ValueError, match="No NWM reaches found"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--point", "-99.321712", "30.069931",
            "--hydrofabric", "test.gdb",
            "--out", str(tmp_path / "forecast.csv"),
        ])



@pytest.mark.parametrize(
    "distance",
    ["0", "-10", "nan", "inf"],
)
def test_operational_cli_point_invalid_distance(
    tmp_path, distance
):
    """Reject invalid search radii before remote retrieval."""
    with pytest.raises(ValueError, match="positive"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--point", "-99.321712", "30.069931",
            "--hydrofabric", str(tmp_path / "missing.gdb"),
            "--max-distance-m", distance,
            "--out", str(tmp_path / "forecast.csv"),
        ])


def test_operational_cli_hydrofabric_without_point(tmp_path):
    """Reject unused hydrofabric arguments."""
    with pytest.raises(ValueError, match="--hydrofabric requires"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--reach", "3586192",
            "--hydrofabric", "test.gdb",
            "--out", str(tmp_path / "forecast.csv"),
        ])


def test_operational_cli_point_duplicate_reach(
    tmp_path, monkeypatch, mock_operational
):
    """Reject a point resolving to an explicitly selected reach."""
    from streamflow_getter import spatial_resolution

    monkeypatch.setattr(
        spatial_resolution,
        "load_nearby_reaches",
        lambda *args, **kwargs: "mocked-geometries",
    )
    monkeypatch.setattr(
        spatial_resolution,
        "nearest_reaches",
        lambda *args, **kwargs: [
            {"feature_id": 3586192, "distance_m": 98.34}
        ],
    )

    with pytest.raises(ValueError, match="Duplicate"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--reach", "3586192",
            "--point", "-99.321712", "30.069931",
            "--hydrofabric", "test.gdb",
            "--out", str(tmp_path / "forecast.csv"),
        ])


def test_operational_cli_point_and_gage(
    tmp_path, monkeypatch, mock_operational
):
    """Combine geographic and USGS selections."""
    from streamflow_getter import (
        spatial_resolution,
        reach_resolution,
    )

    calls, _ = mock_operational

    monkeypatch.setattr(
        spatial_resolution,
        "load_nearby_reaches",
        lambda *args, **kwargs: "mocked-geometries",
    )
    monkeypatch.setattr(
        spatial_resolution,
        "nearest_reaches",
        lambda *args, **kwargs: [
            {"feature_id": 3586192, "distance_m": 98.34}
        ],
    )
    monkeypatch.setattr(
        reach_resolution,
        "load_gage_index",
        lambda path: {"01646500": 4512772},
    )

    result = main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--point", "-99.321712", "30.069931",
        "--hydrofabric", "test.gdb",
        "--gage", "01646500",
        "--routelink", "RouteLink.nc",
        "--out", str(tmp_path / "forecast.csv"),
    ])

    assert result == 0
    assert calls["reaches"] == [3586192, 4512772]


@pytest.mark.parametrize(
    "scenario",
    ["invalid_radius", "no_candidates", "duplicate_reach"],
)
def test_point_errors_never_fetch(
    tmp_path, monkeypatch, scenario
):
    """Geographic selection errors must not trigger remote NWM retrieval."""
    from streamflow_getter import operational_nwm, spatial_resolution

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote NWM retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    monkeypatch.setattr(
        spatial_resolution,
        "load_nearby_reaches",
        lambda *args, **kwargs: "mocked-geometries",
    )

    candidates = (
        []
        if scenario == "no_candidates"
        else [{"feature_id": 3586192, "distance_m": 98.34}]
    )

    monkeypatch.setattr(
        spatial_resolution,
        "nearest_reaches",
        lambda *args, **kwargs: candidates,
    )

    arguments = [
        "nwm-operational",
        "--date", "2026-04-19",
        "--point", "-99.321712", "30.069931",
        "--hydrofabric", "test.gdb",
        "--out", str(tmp_path / "forecast.csv"),
    ]

    if scenario == "invalid_radius":
        arguments.extend(["--max-distance-m", "-10"])

    if scenario == "duplicate_reach":
        arguments.extend(["--reach", "3586192"])

    with pytest.raises(ValueError):
        main(arguments)


def test_operational_cli_bbox_parser():
    parser = build_parser()

    args = parser.parse_args([
        "nwm-operational",
        "--date", "2026-04-19",
        "--bbox", "-99.35", "30.05", "-99.30", "30.09",
        "--hydrofabric", "NWM_v3_hydrofabric.gdb",
        "--out", "forecast.csv",
    ])

    assert args.bbox == [-99.35, 30.05, -99.30, 30.09]
    assert args.hydrofabric == "NWM_v3_hydrofabric.gdb"
    assert args.max_reaches == 100


def test_operational_cli_bbox_custom_limit():
    parser = build_parser()

    args = parser.parse_args([
        "nwm-operational",
        "--date", "2026-04-19",
        "--bbox", "-99.35", "30.05", "-99.30", "30.09",
        "--max-reaches", "25",
        "--out", "forecast.csv",
    ])

    assert args.max_reaches == 25



@pytest.mark.parametrize(
    "selected_ids,maximum,expected_error",
    [
        ([101, 102, 103], 100, None),
        ([], 100, "No NWM reaches found"),
        ([101, 102, 103], 2, "maximum allowed"),
    ],
)
def test_operational_cli_bbox_selection(
    tmp_path,
    monkeypatch,
    mock_operational,
    selected_ids,
    maximum,
    expected_error,
):
    """Validate bbox selection before operational NWM retrieval."""
    from streamflow_getter import (
        operational_nwm,
        spatial_resolution,
    )

    calls, _ = mock_operational

    def fake_bbox(path, bbox):
        assert path == "test.gdb"
        assert bbox == (-99.35, 30.05, -99.30, 30.09)
        return selected_ids

    monkeypatch.setattr(
        spatial_resolution,
        "reaches_in_bbox",
        fake_bbox,
    )

    if expected_error is not None:
        def unexpected_fetch(*args, **kwargs):
            raise AssertionError("Remote NWM retrieval must not run")

        monkeypatch.setattr(
            operational_nwm,
            "fetch_operational_series",
            unexpected_fetch,
        )

    arguments = [
        "nwm-operational",
        "--date", "2026-04-19",
        "--bbox", "-99.35", "30.05", "-99.30", "30.09",
        "--hydrofabric", "test.gdb",
        "--max-reaches", str(maximum),
        "--out", str(tmp_path / "forecast.csv"),
    ]

    if expected_error is not None:
        with pytest.raises(ValueError, match=expected_error):
            main(arguments)
    else:
        assert main(arguments) == 0
        assert calls["reaches"] == selected_ids


def test_operational_cli_bbox_combined_reaches(
    tmp_path, monkeypatch, mock_operational
):
    """Combine bbox and explicit reaches before retrieval."""
    from streamflow_getter import spatial_resolution

    calls, _ = mock_operational

    monkeypatch.setattr(
        spatial_resolution,
        "reaches_in_bbox",
        lambda *args, **kwargs: [101, 102, 103],
    )

    result = main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--bbox", "-99.35", "30.05", "-99.30", "30.09",
        "--hydrofabric", "test.gdb",
        "--reach", "104",
        "--out", str(tmp_path / "forecast.csv"),
    ])

    assert result == 0
    assert calls["reaches"] == [104, 101, 102, 103]


def test_operational_cli_bbox_duplicate_reach(
    tmp_path, monkeypatch
):
    """Reject duplicate IDs before remote retrieval."""
    from streamflow_getter import (
        operational_nwm,
        spatial_resolution,
    )

    monkeypatch.setattr(
        spatial_resolution,
        "reaches_in_bbox",
        lambda *args, **kwargs: [101, 102],
    )

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote NWM retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(ValueError, match="Duplicate"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--bbox", "-99.35", "30.05", "-99.30", "30.09",
            "--hydrofabric", "test.gdb",
            "--reach", "101",
            "--out", str(tmp_path / "forecast.csv"),
        ])


def test_operational_cli_bbox_total_limit(
    tmp_path, monkeypatch
):
    """Apply the reach limit to the combined request."""
    from streamflow_getter import (
        operational_nwm,
        spatial_resolution,
    )

    monkeypatch.setattr(
        spatial_resolution,
        "reaches_in_bbox",
        lambda *args, **kwargs: [101, 102, 103],
    )

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote NWM retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(ValueError, match="maximum allowed"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--bbox", "-99.35", "30.05", "-99.30", "30.09",
            "--hydrofabric", "test.gdb",
            "--reach", "104",
            "--max-reaches", "3",
            "--out", str(tmp_path / "forecast.csv"),
        ])



@pytest.mark.parametrize(
    "bbox",
    [
        (-99.30, 30.05, -99.35, 30.09),  # Reversed west/east
        (-99.35, 30.09, -99.30, 30.05),  # Reversed south/north
        (-200.0, 30.05, -99.30, 30.09), # Invalid longitude
        (-99.35, -100.0, -99.30, 30.09),# Invalid latitude
        (float("nan"), 30.05, -99.30, 30.09),
        (-99.35, 30.05, float("inf"), 30.09),
    ],
)
def test_operational_cli_bbox_invalid_coordinates(
    tmp_path, monkeypatch, bbox
):
    """Reject invalid bbox coordinates before remote NWM access."""
    from streamflow_getter import operational_nwm

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote NWM retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    arguments = [
        "nwm-operational",
        "--date", "2026-04-19",
        "--bbox", *(str(value) for value in bbox),
        "--hydrofabric", str(tmp_path),
        "--out", str(tmp_path / "forecast.csv"),
    ]

    with pytest.raises(ValueError):
        main(arguments)


def test_operational_cli_limit_does_not_change_direct_reaches(
    tmp_path, mock_operational
):
    """Preserve direct-reach requests without geographic bbox limits."""
    calls, _ = mock_operational

    arguments = [
        "nwm-operational",
        "--date", "2026-04-19",
        "--max-reaches", "1",
        "--reach", "101",
        "--reach", "102",
        "--out", str(tmp_path / "forecast.csv"),
    ]

    assert main(arguments) == 0
    assert calls["reaches"] == [101, 102]


def test_operational_cli_polygon_parser():
    """Parse a polygon selection without loading geographic data."""
    parser = build_parser()

    args = parser.parse_args([
        "nwm-operational",
        "--date", "2026-04-19",
        "--polygon", "region.geojson",
        "--hydrofabric", "NWM_v3_hydrofabric.gdb",
        "--out", "forecast.csv",
    ])

    assert args.polygon == "region.geojson"
    assert args.hydrofabric == "NWM_v3_hydrofabric.gdb"
    assert args.max_reaches == 100



@pytest.mark.parametrize(
    "selected_ids,maximum,expected_error",
    [
        ([101, 102, 103], 100, None),
        ([], 100, "No NWM reaches found"),
        ([101, 102, 103], 2, "maximum allowed"),
    ],
)
def test_operational_cli_polygon_selection(
    tmp_path,
    monkeypatch,
    mock_operational,
    selected_ids,
    maximum,
    expected_error,
):
    """Validate polygon selection before remote NWM retrieval."""
    from shapely.geometry import box

    from streamflow_getter import (
        operational_nwm,
        spatial_resolution,
    )

    calls, _ = mock_operational
    polygon = box(-99.35, 30.05, -99.30, 30.09)

    monkeypatch.setattr(
        spatial_resolution,
        "load_geojson_polygon",
        lambda path: polygon,
    )

    def fake_polygon_selection(path, geometry):
        assert path == "test.gdb"
        assert geometry.equals(polygon)
        return selected_ids

    monkeypatch.setattr(
        spatial_resolution,
        "reaches_in_polygon",
        fake_polygon_selection,
    )

    if expected_error is not None:
        def unexpected_fetch(*args, **kwargs):
            raise AssertionError("Remote NWM retrieval must not run")

        monkeypatch.setattr(
            operational_nwm,
            "fetch_operational_series",
            unexpected_fetch,
        )

    arguments = [
        "nwm-operational",
        "--date", "2026-04-19",
        "--polygon", "region.geojson",
        "--hydrofabric", "test.gdb",
        "--max-reaches", str(maximum),
        "--out", str(tmp_path / "forecast.csv"),
    ]

    if expected_error is not None:
        with pytest.raises(ValueError, match=expected_error):
            main(arguments)
    else:
        assert main(arguments) == 0
        assert calls["reaches"] == selected_ids


@pytest.mark.parametrize(
    "scenario",
    ["missing_file", "invalid_geometry", "duplicate_reach"],
)
def test_operational_cli_polygon_errors_never_fetch(
    tmp_path, monkeypatch, scenario
):
    """Reject invalid polygon selections before remote NWM access."""
    import json

    from streamflow_getter import operational_nwm, spatial_resolution

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote NWM retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    polygon_path = tmp_path / "region.geojson"

    if scenario == "missing_file":
        expected_error = FileNotFoundError

    elif scenario == "invalid_geometry":
        polygon_path.write_text(json.dumps({
            "type": "Point",
            "coordinates": [-99.32, 30.07],
        }))
        expected_error = ValueError

    else:
        from shapely.geometry import box

        polygon_path.write_text(json.dumps({
            "type": "Polygon",
            "coordinates": [[
                [-99.35, 30.05],
                [-99.30, 30.05],
                [-99.30, 30.09],
                [-99.35, 30.09],
                [-99.35, 30.05],
            ]],
        }))

        monkeypatch.setattr(
            spatial_resolution,
            "reaches_in_polygon",
            lambda *args, **kwargs: [3586192],
        )
        expected_error = ValueError

    arguments = [
        "nwm-operational",
        "--date", "2026-04-19",
        "--polygon", str(polygon_path),
        "--hydrofabric", "test.gdb",
        "--out", str(tmp_path / "forecast.csv"),
    ]

    if scenario == "duplicate_reach":
        arguments.extend(["--reach", "3586192"])

    with pytest.raises(expected_error):
        main(arguments)


def test_operational_cli_polygon_malformed_json_never_fetch(
    tmp_path, monkeypatch
):
    """Reject malformed GeoJSON before remote NWM retrieval."""
    from streamflow_getter import operational_nwm

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote NWM retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    polygon_path = tmp_path / "invalid.geojson"
    polygon_path.write_text(
        '{"type": "Polygon", "coordinates": [',
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--polygon", str(polygon_path),
            "--hydrofabric", "test.gdb",
            "--out", str(tmp_path / "forecast.csv"),
        ])


def test_operational_cli_polygon_combined_reach_limit(
    tmp_path, monkeypatch
):
    """Enforce the regional limit on combined polygon selections."""
    from shapely.geometry import box
    from streamflow_getter import operational_nwm, spatial_resolution

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Remote NWM retrieval must not run")

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    monkeypatch.setattr(
        spatial_resolution,
        "load_geojson_polygon",
        lambda path: box(-99.35, 30.05, -99.30, 30.09),
    )

    monkeypatch.setattr(
        spatial_resolution,
        "reaches_in_polygon",
        lambda *args, **kwargs: [101, 102, 103],
    )

    with pytest.raises(ValueError, match="maximum allowed"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--polygon", "region.geojson",
            "--hydrofabric", "test.gdb",
            "--reach", "104",
            "--max-reaches", "3",
            "--out", str(tmp_path / "forecast.csv"),
        ])


def test_operational_cli_product_parser():
    """Preserve the default and accept the validated medium-range product."""
    parser = build_parser()

    default = parser.parse_args([
        "nwm-operational",
        "--date", "2026-04-19",
        "--reach", "3586192",
        "--out", "forecast.csv",
    ])

    assert default.product == "short_range"

    medium = parser.parse_args([
        "nwm-operational",
        "--date", "2026-04-19",
        "--product", "medium_range_mem1",
        "--reach", "3586192",
        "--out", "medium.csv",
    ])

    assert medium.product == "medium_range_mem1"


def test_operational_cli_medium_range_config(mock_operational):
    """Pass the selected product to the existing retrieval backend."""
    calls, _ = mock_operational

    main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--cycle", "6",
        "--product", "medium_range_mem1",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "2",
        "--out", "medium.csv",
    ])

    assert calls["config"].product == "medium_range_mem1"
    assert calls["config"].cycle == 6
    assert calls["start_hour"] == 1
    assert calls["end_hour"] == 2


@pytest.mark.parametrize("cycle", [1, 3, 9, 23])
def test_operational_cli_medium_range_invalid_cycle(
    mock_operational, cycle
):
    """Reject unsupported medium-range cycles before retrieval."""
    calls, _ = mock_operational

    with pytest.raises(ValueError, match="cycle"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--cycle", str(cycle),
            "--product", "medium_range_mem1",
            "--reach", "3586192",
            "--out", "medium.csv",
        ])

    assert "reaches" not in calls


@pytest.mark.parametrize("start_hour,end_hour", [
    (1, 241),
    (239, 241),
    (241, 241),
])
def test_operational_cli_medium_range_invalid_hours(
    mock_operational, start_hour, end_hour
):
    """Reject unsupported forecast hours before retrieval."""
    calls, _ = mock_operational

    with pytest.raises(ValueError, match="Forecast hour"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--product", "medium_range_mem1",
            "--reach", "3586192",
            "--start-hour", str(start_hour),
            "--end-hour", str(end_hour),
            "--out", "medium.csv",
        ])

    assert "reaches" not in calls


@pytest.mark.parametrize("member", range(2, 7))
def test_operational_cli_additional_medium_range_members(
    mock_operational, member
):
    """Pass each supported ensemble member to the retrieval backend."""
    calls, _ = mock_operational
    product = f"medium_range_mem{member}"

    main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--cycle", "0",
        "--product", product,
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "2",
        "--out", "medium.csv",
    ])

    assert calls["config"].product == product
    assert calls["config"].spec.max_hour == 204
    assert calls["start_hour"] == 1
    assert calls["end_hour"] == 2


@pytest.mark.parametrize("member", range(2, 7))
def test_operational_cli_additional_members_reject_hour_205(
    mock_operational, member
):
    """Reject unsupported lead hours before remote retrieval."""
    calls, _ = mock_operational

    with pytest.raises(ValueError, match="Forecast hour"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--cycle", "0",
            "--product", f"medium_range_mem{member}",
            "--reach", "3586192",
            "--start-hour", "1",
            "--end-hour", "205",
            "--out", "medium.csv",
        ])

    assert "reaches" not in calls


def test_operational_cli_medium_range_blend(mock_operational):
    calls, _ = mock_operational

    main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--cycle", "0",
        "--product", "medium_range_blend",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "2",
        "--out", "blend.csv",
    ])

    assert calls["config"].product == "medium_range_blend"
    assert calls["config"].spec.max_hour == 240
    assert calls["start_hour"] == 1
    assert calls["end_hour"] == 2


def test_operational_cli_medium_range_blend_rejects_hour_241(
    mock_operational,
):
    calls, _ = mock_operational

    with pytest.raises(ValueError, match="Forecast hour"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--cycle", "0",
            "--product", "medium_range_blend",
            "--reach", "3586192",
            "--start-hour", "1",
            "--end-hour", "241",
            "--out", "blend.csv",
        ])

    assert "reaches" not in calls


def test_operational_cli_medium_range_no_da(mock_operational):
    calls, _ = mock_operational

    main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--cycle", "0",
        "--product", "medium_range_no_da",
        "--reach", "3586192",
        "--start-hour", "4",
        "--end-hour", "12",
        "--out", "no_da.csv",
    ])

    assert calls["config"].product == "medium_range_no_da"
    assert calls["config"].spec.analysis_product == "analysis_assim_no_da"
    assert calls["config"].forecast_hours(4, 12) == [6, 9, 12]


def test_operational_cli_medium_range_no_da_empty_window(
    mock_operational,
):
    calls, _ = mock_operational

    with pytest.raises(ValueError, match="No available forecast leads"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--cycle", "0",
            "--product", "medium_range_no_da",
            "--reach", "3586192",
            "--start-hour", "1",
            "--end-hour", "2",
            "--out", "no_da.csv",
        ])

    assert "reaches" not in calls


def test_operational_cli_long_range_mem1(mock_operational):
    calls, _ = mock_operational

    main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--cycle", "0",
        "--product", "long_range_mem1",
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "24",
        "--out", "long_range.csv",
    ])

    assert calls["config"].product == "long_range_mem1"
    assert calls["config"].spec.max_hour == 720
    assert calls["config"].forecast_hours(1, 24) == [
        6, 12, 18, 24
    ]


def test_operational_cli_long_range_mem1_empty_window(
    mock_operational,
):
    calls, _ = mock_operational

    with pytest.raises(ValueError, match="No available forecast leads"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--cycle", "0",
            "--product", "long_range_mem1",
            "--reach", "3586192",
            "--start-hour", "1",
            "--end-hour", "5",
            "--out", "long_range.csv",
        ])

    assert "reaches" not in calls


@pytest.mark.parametrize("member", [2, 3, 4])
def test_operational_cli_long_range_ensemble(
    mock_operational, member
):
    calls, _ = mock_operational
    product = f"long_range_mem{member}"

    main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--cycle", "0",
        "--product", product,
        "--reach", "3586192",
        "--start-hour", "1",
        "--end-hour", "24",
        "--out", "long_range.csv",
    ])

    assert calls["config"].product == product
    assert calls["config"].spec.max_hour == 720
    assert calls["config"].forecast_hours(1, 24) == [
        6, 12, 18, 24
    ]


@pytest.mark.parametrize("member", [2, 3, 4])
def test_operational_cli_long_range_ensemble_empty_window(
    mock_operational, member
):
    calls, _ = mock_operational
    product = f"long_range_mem{member}"

    with pytest.raises(ValueError, match="No available forecast leads"):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--cycle", "0",
            "--product", product,
            "--reach", "3586192",
            "--start-hour", "1",
            "--end-hour", "5",
            "--out", "long_range.csv",
        ])

    assert "reaches" not in calls

def test_operational_cli_known_routelink_match_records_provenance(
    tmp_path,
    monkeypatch,
    mock_operational,
):
    """Allow a known matching RouteLink and preserve provenance."""
    from streamflow_getter import reach_resolution

    calls, _ = mock_operational

    monkeypatch.setattr(
        reach_resolution,
        "load_gage_index",
        lambda path: {
            "07166500": 20955128,
        },
    )

    monkeypatch.setattr(
        reach_resolution,
        "classify_gage_index_version",
        lambda index: {
            "crosswalk_sha256": (
                "c0ee33504fd74319e68ba07b370110d0"
                "22efe09a76a022ccb7361921fc909ec6"
            ),
            "network_version": "3.1",
            "gage_count": 8735,
        },
    )

    assert main([
        "nwm-operational",
        "--date", "2026-11-10",
        "--cycle", "0",
        "--gage", "07166500",
        "--routelink", str(
            tmp_path
            / "RouteLink_CONUS.nc"
        ),
        "--out", str(
            tmp_path
            / "forecast.csv"
        ),
    ]) == 0

    assert calls[
        "reaches"
    ] == [
        20955128,
    ]

    assert calls[
        "manifest"
    ][
        "selection"
    ][
        "spatial"
    ] == {
        "gage_resolution": {
            "gage_ids": [
                "07166500",
            ],
            "resolved_gages": {
                "07166500":
                    20955128,
            },
            "routelink": {
                "file_name":
                    "RouteLink_CONUS.nc",
                "crosswalk_sha256": (
                    "c0ee33504fd74319e68ba07b370110d0"
                    "22efe09a76a022ccb7361921fc909ec6"
                ),
                "network_version":
                    "3.1",
                "gage_count":
                    8735,
                "compatibility":
                    "compatible",
                "requested_nwm_versions":
                    ["3.1"],
                "unresolved_request_version_count":
                    0,
            },
        },
    }


def test_operational_cli_known_routelink_mismatch_stops_before_fetch(
    tmp_path,
    monkeypatch,
):
    """Reject a known v3.1 RouteLink for an NWM 3.0 request."""
    from streamflow_getter import (
        operational_nwm,
        reach_resolution,
    )

    monkeypatch.setattr(
        reach_resolution,
        "load_gage_index",
        lambda path: {
            "07166500": 20955128,
        },
    )

    monkeypatch.setattr(
        reach_resolution,
        "classify_gage_index_version",
        lambda index: {
            "crosswalk_sha256": (
                "c0ee33504fd74319e68ba07b370110d0"
                "22efe09a76a022ccb7361921fc909ec6"
            ),
            "network_version": "3.1",
            "gage_count": 8735,
        },
    )

    def unexpected_fetch(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "Remote NWM retrieval must not run"
        )

    monkeypatch.setattr(
        operational_nwm,
        "fetch_operational_series",
        unexpected_fetch,
    )

    with pytest.raises(
        ValueError,
        match="incompatible",
    ):
        main([
            "nwm-operational",
            "--date", "2026-04-19",
            "--cycle", "0",
            "--gage", "07166500",
            "--routelink", str(
                tmp_path
                / "RouteLink_CONUS.nc"
            ),
            "--out", str(
                tmp_path
                / "forecast.csv"
            ),
        ])


def test_operational_cli_cross_version_period_stops_before_fetch(
    tmp_path,
    monkeypatch,
):
    """Reject one RouteLink for a request spanning NWM 3.0 and 3.1."""
    from streamflow_getter import (
        operational_requests,
        reach_resolution,
    )

    monkeypatch.setattr(
        reach_resolution,
        "load_gage_index",
        lambda path: {
            "07166500": 20955128,
        },
    )

    monkeypatch.setattr(
        reach_resolution,
        "classify_gage_index_version",
        lambda index: {
            "crosswalk_sha256": (
                "c0ee33504fd74319e68ba07b370110d0"
                "22efe09a76a022ccb7361921fc909ec6"
            ),
            "network_version": "3.1",
            "gage_count": 8735,
        },
    )

    def unexpected_fetch(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "Remote NWM retrieval must not run"
        )

    monkeypatch.setattr(
        operational_requests,
        "fetch_operational_configs",
        unexpected_fetch,
    )

    with pytest.raises(
        ValueError,
        match=r"3\.0, 3\.1",
    ):
        main([
            "nwm-operational",
            "--start-date", "2026-08-17",
            "--end-date", "2026-08-18",
            "--cycle", "12",
            "--gage", "07166500",
            "--routelink", str(
                tmp_path
                / "RouteLink_CONUS.nc"
            ),
            "--out", str(
                tmp_path
                / "forecast.csv"
            ),
        ])


def test_operational_cli_unknown_routelink_allowed_and_recorded(
    tmp_path,
    monkeypatch,
    mock_operational,
):
    """Unknown RouteLinks remain usable but explicitly unverified."""
    from streamflow_getter import reach_resolution

    calls, _ = mock_operational

    monkeypatch.setattr(
        reach_resolution,
        "load_gage_index",
        lambda path: {
            "08165500": 3586192,
        },
    )

    unknown_digest = (
        "0" * 64
    )

    monkeypatch.setattr(
        reach_resolution,
        "classify_gage_index_version",
        lambda index: {
            "crosswalk_sha256":
                unknown_digest,
            "network_version":
                None,
            "gage_count":
                1,
        },
    )

    assert main([
        "nwm-operational",
        "--date", "2026-04-19",
        "--gage", "08165500",
        "--routelink", str(
            tmp_path
            / "custom.nc"
        ),
        "--out", str(
            tmp_path
            / "forecast.csv"
        ),
    ]) == 0

    routelink = (
        calls[
            "manifest"
        ][
            "selection"
        ][
            "spatial"
        ][
            "gage_resolution"
        ][
            "routelink"
        ]
    )

    assert routelink[
        "network_version"
    ] is None

    assert routelink[
        "crosswalk_sha256"
    ] == unknown_digest

    assert routelink[
        "compatibility"
    ] == (
        "unknown_routelink_version"
    )

    assert routelink[
        "requested_nwm_versions"
    ] == [
        "3.0",
    ]

    assert routelink[
        "unresolved_request_version_count"
    ] == 0
