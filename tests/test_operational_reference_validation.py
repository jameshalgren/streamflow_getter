"""Tests for operational NWM Kerchunk reference validation."""

import pytest

from streamflow_getter.reference_validation import (
    validate_reference,
    valid_source_identity,
)


@pytest.fixture
def reference():
    url = "https://example.com/nwm.nc"
    return {
        "version": 1,
        "refs": {
            ".zgroup": '{"zarr_format":2}',
            "feature_id/.zarray": "{}",
            "feature_id/0": [url, 0, 100],
            "streamflow/.zarray": "{}",
            "streamflow/0": [url, 100, 200],
        },
    }


def test_valid_reference(reference):
    assert validate_reference(reference)
    assert valid_source_identity(
        reference, "https://example.com/nwm.nc"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_version",
        "missing_key",
        "missing_refs",
        "invalid_refs",
        "wrong_offset",
        "zero_length",
        "wrong_offset_type",
        "wrong_length_type",
        "boolean_offset",
        "invalid_scheme",
    ],
)
def test_invalid_reference(reference, mutation):
    if mutation == "wrong_version":
        reference["version"] = 2
    elif mutation == "missing_key":
        del reference["refs"]["streamflow/0"]
    elif mutation == "missing_refs":
        del reference["refs"]
    elif mutation == "invalid_refs":
        reference["refs"] = []
    else:
        chunk = reference["refs"]["streamflow/0"]
        if mutation == "wrong_offset":
            chunk[1] = -1
        elif mutation == "zero_length":
            chunk[2] = 0
        elif mutation == "wrong_offset_type":
            chunk[1] = "0"
        elif mutation == "wrong_length_type":
            chunk[2] = "100"
        elif mutation == "boolean_offset":
            chunk[1] = True
        elif mutation == "invalid_scheme":
            chunk[0] = "ftp://example.com/nwm.nc"

    assert not validate_reference(reference)


def test_invalid_reference_type():
    assert not validate_reference([])


def test_wrong_source(reference):
    assert not valid_source_identity(
        reference, "https://example.com/other.nc"
    )


def test_mixed_sources(reference):
    reference["refs"]["streamflow/0"][0] = (
        "https://example.com/other.nc"
    )
    assert not valid_source_identity(
        reference, "https://example.com/nwm.nc"
    )


def test_invalid_expected_url(reference):
    assert not valid_source_identity(reference, "")


def test_valid_additional_chunk(reference):
    reference["refs"]["velocity/0"] = [
        "https://example.com/nwm.nc", 200, 100
    ]
    assert validate_reference(reference)
    assert valid_source_identity(
        reference, "https://example.com/nwm.nc"
    )


def test_invalid_additional_chunk(reference):
    reference["refs"]["velocity/0"] = [
        "https://example.com/nwm.nc", -10, 100
    ]
    assert not validate_reference(reference)


def test_wrong_source_in_additional_chunk(reference):
    reference["refs"]["velocity/0"] = [
        "https://example.com/other.nc", 200, 100
    ]
    assert not valid_source_identity(
        reference, "https://example.com/nwm.nc"
    )


def test_valid_historical_template(reference):
    expected_url = (
        "https://storage.googleapis.com/"
        "national-water-model/nwm.nc"
    )
    reference["templates"] = {"u": expected_url}
    reference["refs"]["feature_id/0"][0] = "{{u}}"
    reference["refs"]["streamflow/0"][0] = "{{u}}"

    assert validate_reference(reference)
    assert valid_source_identity(reference, expected_url)


@pytest.mark.parametrize(
    "template_value",
    [None, "", "ftp://example.com/nwm.nc", "{{other}}"],
)
def test_invalid_historical_template(reference, template_value):
    reference["templates"] = {"u": template_value}
    reference["refs"]["feature_id/0"][0] = "{{u}}"

    assert not validate_reference(reference)


def test_undefined_historical_template(reference):
    reference["refs"]["feature_id/0"][0] = "{{missing}}"
    assert not validate_reference(reference)


def test_historical_template_wrong_source(reference):
    reference["templates"] = {
        "u": "https://example.com/another-file.nc"
    }
    reference["refs"]["feature_id/0"][0] = "{{u}}"
    reference["refs"]["streamflow/0"][0] = "{{u}}"

    assert validate_reference(reference)
    assert not valid_source_identity(
        reference, "https://example.com/nwm.nc"
    )


@pytest.mark.parametrize("offset,length", [(-1, 100), (0, 0)])
def test_invalid_historical_byte_range(reference, offset, length):
    reference["templates"] = {
        "u": "https://example.com/nwm.nc"
    }
    reference["refs"]["feature_id/0"] = [
        "{{u}}", offset, length
    ]
    assert not validate_reference(reference)
