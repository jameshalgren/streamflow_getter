
"""Tests for CSV and Parquet streamflow output."""

from pathlib import Path

import pandas as pd
import pytest

from streamflow_getter.output import (
    manifest_path_for,
    resolve_output_format,
    write_manifest,
    write_timeseries,
    write_timeseries_with_manifest,
)


@pytest.fixture
def sample_frame():
    return pd.DataFrame({
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


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("flow.csv", "csv"),
        ("flow.CSV", "csv"),
        ("flow.parquet", "parquet"),
        ("flow.PARQUET", "parquet"),
    ],
)
def test_format_inference(filename, expected):
    assert resolve_output_format(filename) == expected


def test_explicit_format():
    assert resolve_output_format(
        "flow.data", "parquet"
    ) == "parquet"


@pytest.mark.parametrize(
    "filename",
    ["flow", "flow.txt", "flow.json"],
)
def test_unsupported_extension(filename):
    with pytest.raises(ValueError):
        resolve_output_format(filename)


@pytest.mark.parametrize(
    "output_format",
    ["json", "", 123],
)
def test_invalid_explicit_format(output_format):
    with pytest.raises(ValueError):
        resolve_output_format(
            "flow.csv", output_format
        )


def test_csv_roundtrip(tmp_path, sample_frame):
    path = tmp_path / "flow.csv"

    result = write_timeseries(sample_frame, path)

    assert result == path
    assert path.exists()

    restored = pd.read_csv(path)

    assert list(restored.columns) == list(sample_frame.columns)
    assert restored["lead_hour"].tolist() == [0, 1]
    assert restored["product"].tolist() == [
        "analysis_assim",
        "short_range",
    ]
    assert restored["reference_time"].tolist() == [
        "2026-04-18T21:00:00",
        "2026-04-19T00:00:00",
    ]


def test_parquet_roundtrip(tmp_path, sample_frame):
    path = tmp_path / "flow.parquet"

    result = write_timeseries(sample_frame, path)

    assert result == path

    restored = pd.read_parquet(path)

    pd.testing.assert_frame_equal(
        restored,
        sample_frame,
    )


def test_existing_file_preserved(tmp_path, sample_frame):
    path = tmp_path / "flow.csv"
    path.write_text("existing-content")

    with pytest.raises(FileExistsError):
        write_timeseries(sample_frame, path)

    assert path.read_text() == "existing-content"


def test_empty_frame_rejected(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        write_timeseries(
            pd.DataFrame(),
            tmp_path / "flow.csv",
        )


def test_invalid_frame_rejected(tmp_path):
    with pytest.raises(TypeError):
        write_timeseries(
            {"streamflow": [0.41]},
            tmp_path / "flow.csv",
        )


def test_failed_serialization_cleans_temporary_file(
    tmp_path, sample_frame, monkeypatch
):
    path = tmp_path / "flow.csv"

    def failing_to_csv(self, *args, **kwargs):
        raise RuntimeError("Simulated serialization failure")

    monkeypatch.setattr(
        pd.DataFrame,
        "to_csv",
        failing_to_csv,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated serialization failure",
    ):
        write_timeseries(sample_frame, path)

    assert not path.exists()
    assert not list(tmp_path.glob(".streamflow-output-*.tmp"))



def test_publication_failure_cleans_destination(
    tmp_path, sample_frame, monkeypatch
):
    """Remove incomplete output when publication fails."""
    path = tmp_path / "flow.csv"

    original_open = Path.open

    class FailingOutput:
        def __init__(self, file):
            self.file = file

        def __enter__(self):
            self.file.__enter__()
            return self

        def __exit__(self, *args):
            return self.file.__exit__(*args)

        def write(self, data):
            self.file.write(data[:5])
            raise OSError("Simulated publication failure")

    def patched_open(self, mode="r", *args, **kwargs):
        file = original_open(self, mode, *args, **kwargs)

        if self == path and mode == "xb":
            return FailingOutput(file)

        return file

    monkeypatch.setattr(Path, "open", patched_open)

    with pytest.raises(
        OSError,
        match="Simulated publication failure",
    ):
        write_timeseries(sample_frame, path)

    assert not path.exists()
    assert not list(tmp_path.glob(".streamflow-output-*.tmp"))


@pytest.mark.parametrize(
    "filename,output_format",
    [
        ("flow.csv", "parquet"),
        ("flow.parquet", "csv"),
    ],
)
def test_conflicting_output_format(filename, output_format):
    with pytest.raises(ValueError, match="conflicts"):
        resolve_output_format(filename, output_format)

def test_default_manifest_path_preserves_data_extension(tmp_path):
    assert manifest_path_for(
        tmp_path / "flow.csv"
    ) == (
        tmp_path
        / "flow.csv.manifest.json"
    )

    assert manifest_path_for(
        tmp_path / "flow.parquet"
    ) == (
        tmp_path
        / "flow.parquet.manifest.json"
    )


def test_manifest_roundtrip(tmp_path):
    import json

    path = (
        tmp_path
        / "flow.csv.manifest.json"
    )

    manifest = {
        "schema_version": 1,
        "status": "complete",
        "result": {
            "row_count": 2,
        },
    }

    result = write_manifest(
        manifest,
        path,
    )

    assert result == path

    with path.open(
        encoding="utf-8"
    ) as file:
        restored = json.load(
            file
        )

    assert restored == manifest

    raw = path.read_text(
        encoding="utf-8"
    )

    assert raw.endswith("\n")


def test_manifest_existing_file_is_preserved(tmp_path):
    path = (
        tmp_path
        / "flow.csv.manifest.json"
    )

    path.write_text(
        "existing-manifest",
        encoding="utf-8",
    )

    with pytest.raises(
        FileExistsError,
        match="already exists",
    ):
        write_manifest(
            {
                "schema_version": 1,
            },
            path,
        )

    assert path.read_text(
        encoding="utf-8"
    ) == "existing-manifest"


@pytest.mark.parametrize(
    "manifest,error_type",
    [
        (
            ["not", "a", "mapping"],
            TypeError,
        ),
        (
            {
                "not_json": object(),
            },
            ValueError,
        ),
        (
            {
                "not_strict_json": float("nan"),
            },
            ValueError,
        ),
    ],
)
def test_manifest_rejects_invalid_content_before_publication(
    tmp_path,
    manifest,
    error_type,
):
    path = (
        tmp_path
        / "flow.csv.manifest.json"
    )

    with pytest.raises(
        error_type,
    ):
        write_manifest(
            manifest,
            path,
        )

    assert not path.exists()

    assert not list(
        tmp_path.glob(
            ".streamflow-manifest-*.tmp"
        )
    )


def test_manifest_publication_failure_cleans_temporary_file(
    tmp_path,
    monkeypatch,
):
    import os

    path = (
        tmp_path
        / "flow.csv.manifest.json"
    )

    original_link = os.link

    def failing_link(source, destination, *args, **kwargs):
        if Path(destination) == path:
            raise OSError(
                "Simulated manifest publication failure"
            )

        return original_link(
            source,
            destination,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        os,
        "link",
        failing_link,
    )

    with pytest.raises(
        OSError,
        match="Simulated manifest publication failure",
    ):
        write_manifest(
            {
                "schema_version": 1,
                "status": "complete",
            },
            path,
        )

    assert not path.exists()

    assert not list(
        tmp_path.glob(
            ".streamflow-manifest-*.tmp"
        )
    )


def test_timeseries_with_manifest_publishes_both(
    tmp_path,
    sample_frame,
):
    import json

    data_path = (
        tmp_path
        / "flow.csv"
    )

    manifest = {
        "schema_version": 1,
        "status": "complete",
        "result": {
            "row_count": len(
                sample_frame
            ),
        },
    }

    data_result, manifest_result = (
        write_timeseries_with_manifest(
            sample_frame,
            data_path,
            manifest,
        )
    )

    expected_manifest = (
        tmp_path
        / "flow.csv.manifest.json"
    )

    assert data_result == data_path
    assert manifest_result == expected_manifest

    restored = pd.read_csv(
        data_result
    )

    assert list(
        restored.columns
    ) == list(
        sample_frame.columns
    )

    with manifest_result.open(
        encoding="utf-8"
    ) as file:
        restored_manifest = json.load(
            file
        )

    assert restored_manifest == manifest


def test_timeseries_with_manifest_accepts_custom_sidecar(
    tmp_path,
    sample_frame,
):
    data_path = (
        tmp_path
        / "flow.csv"
    )

    manifest_path = (
        tmp_path
        / "run-manifest.json"
    )

    results = write_timeseries_with_manifest(
        sample_frame,
        data_path,
        {
            "schema_version": 1,
            "status": "complete",
        },
        manifest_path=manifest_path,
    )

    assert results == (
        data_path,
        manifest_path,
    )

    assert data_path.exists()
    assert manifest_path.exists()


def test_timeseries_with_manifest_rejects_existing_sidecar_before_data(
    tmp_path,
    sample_frame,
):
    data_path = (
        tmp_path
        / "flow.csv"
    )

    manifest_path = manifest_path_for(
        data_path
    )

    manifest_path.write_text(
        "preserve-me",
        encoding="utf-8",
    )

    with pytest.raises(
        FileExistsError,
        match="Manifest already exists",
    ):
        write_timeseries_with_manifest(
            sample_frame,
            data_path,
            {
                "schema_version": 1,
            },
        )

    assert not data_path.exists()

    assert manifest_path.read_text(
        encoding="utf-8"
    ) == "preserve-me"


def test_timeseries_with_manifest_rejects_existing_data_before_sidecar(
    tmp_path,
    sample_frame,
):
    data_path = (
        tmp_path
        / "flow.csv"
    )

    data_path.write_text(
        "preserve-data",
        encoding="utf-8",
    )

    manifest_path = manifest_path_for(
        data_path
    )

    with pytest.raises(
        FileExistsError,
        match="Output already exists",
    ):
        write_timeseries_with_manifest(
            sample_frame,
            data_path,
            {
                "schema_version": 1,
            },
        )

    assert data_path.read_text(
        encoding="utf-8"
    ) == "preserve-data"

    assert not manifest_path.exists()


def test_timeseries_with_manifest_validates_manifest_before_data(
    tmp_path,
    sample_frame,
):
    data_path = (
        tmp_path
        / "flow.csv"
    )

    with pytest.raises(
        ValueError,
        match="strict JSON-compatible",
    ):
        write_timeseries_with_manifest(
            sample_frame,
            data_path,
            {
                "not_json": object(),
            },
        )

    assert not data_path.exists()
    assert not manifest_path_for(
        data_path
    ).exists()


def test_timeseries_with_manifest_rolls_back_data_on_sidecar_failure(
    tmp_path,
    sample_frame,
    monkeypatch,
):
    from streamflow_getter import output

    data_path = (
        tmp_path
        / "flow.csv"
    )

    manifest_path = manifest_path_for(
        data_path
    )

    def failing_publish(payload, destination):
        assert Path(
            destination
        ) == manifest_path

        assert data_path.exists()

        raise OSError(
            "Controlled sidecar failure"
        )

    monkeypatch.setattr(
        output,
        "_publish_manifest_payload",
        failing_publish,
    )

    with pytest.raises(
        OSError,
        match="Controlled sidecar failure",
    ):
        write_timeseries_with_manifest(
            sample_frame,
            data_path,
            {
                "schema_version": 1,
                "status": "complete",
            },
        )

    assert not data_path.exists()
    assert not manifest_path.exists()


def test_timeseries_with_manifest_requires_distinct_paths(
    tmp_path,
    sample_frame,
):
    path = (
        tmp_path
        / "flow.csv"
    )

    with pytest.raises(
        ValueError,
        match="must differ",
    ):
        write_timeseries_with_manifest(
            sample_frame,
            path,
            {
                "schema_version": 1,
            },
            manifest_path=path,
        )

    assert not path.exists()
