"""Tests for Kerchunk reference structural validation."""

import pytest

from streamflow_getter.reference_validation import (
    validate_reference,
    valid_source_identity,
)


@pytest.fixture
def valid_reference():
    return {
        "version": 1,
        "refs": {
            ".zgroup": '{"zarr_format":2}',
            "feature_id/.zarray": "{}",
            "feature_id/0": ["https://example.org/data.nc", 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": ["https://example.org/data.nc", 100, 200],
        },
    }


def test_valid_reference(valid_reference):
    assert validate_reference(valid_reference)


def test_missing_required_key(valid_reference):
    del valid_reference["refs"]["streamflow/0"]
    assert not validate_reference(valid_reference)


def test_wrong_version(valid_reference):
    valid_reference["version"] = 2
    assert not validate_reference(valid_reference)


def test_missing_refs(valid_reference):
    del valid_reference["refs"]
    assert not validate_reference(valid_reference)


def test_invalid_reference_type():
    assert not validate_reference([])


def test_invalid_refs_type(valid_reference):
    valid_reference["refs"] = []
    assert not validate_reference(valid_reference)


def test_correct_source_identity(valid_reference):
    expected = "https://example.org/data.nc"

    assert valid_source_identity(valid_reference, expected)


def test_incorrect_source_identity(valid_reference):
    expected = "https://example.org/other.nc"

    assert not valid_source_identity(valid_reference, expected)


def test_mixed_source_identity(valid_reference):
    valid_reference["refs"]["streamflow/0"][0] = (
        "https://example.org/other.nc"
    )

    assert not valid_source_identity(
        valid_reference,
        "https://example.org/data.nc",
    )


def test_invalid_expected_url(valid_reference):
    assert not valid_source_identity(valid_reference, "")

def test_invalid_additional_chunk(valid_reference):
    valid_reference["refs"]["velocity/0"] = [
        "https://example.org/data.nc",
        -10,
        100,
    ]

    assert not validate_reference(valid_reference)


def test_wrong_source_in_additional_chunk(valid_reference):
    valid_reference["refs"]["velocity/0"] = [
        "https://example.org/wrong.nc",
        200,
        100,
    ]

    assert not valid_source_identity(
        valid_reference,
        "https://example.org/data.nc",
    )


def test_valid_additional_chunk(valid_reference):
    valid_reference["refs"]["velocity/0"] = [
        "https://example.org/data.nc",
        200,
        100,
    ]

    assert validate_reference(valid_reference)

    assert valid_source_identity(
        valid_reference,
        "https://example.org/data.nc",
    )


@pytest.mark.parametrize(
    "invalid_range",
    [
        ["https://example.org/data.nc", -1, 100],
        ["https://example.org/data.nc", 0, 0],
        ["https://example.org/data.nc", 0, -100],
        ["https://example.org/data.nc", "0", 100],
        ["https://example.org/data.nc", 0, "100"],
        ["https://example.org/data.nc", True, 100],
        ["ftp://example.org/data.nc", 0, 100],
        ["https://example.org/data.nc", 0],
        None,
    ],
)


def test_invalid_byte_range(valid_reference, invalid_range):
    valid_reference["refs"]["streamflow/0"] = invalid_range
    assert not validate_reference(valid_reference)