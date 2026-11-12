"""Tests for NWM cache metadata comparison."""

import pytest

from streamflow_getter.reference_cache import compare_metadata


@pytest.fixture
def cached():
    return {
        "reference_etag": "etag-a",
        "source_generation": "generation-1",
    }


def test_unchanged(cached):
    assert compare_metadata(cached, cached.copy()) == "unchanged"


def test_reference_changed(cached):
    current = cached.copy()
    current["reference_etag"] = "etag-b"

    assert compare_metadata(cached, current) == "reference_changed"


def test_source_changed(cached):
    current = cached.copy()
    current["source_generation"] = "generation-2"

    assert compare_metadata(cached, current) == "source_changed"


def test_missing_metadata(cached):
    current = cached.copy()
    del current["source_generation"]

    assert compare_metadata(cached, current) == "unknown"


def test_both_changed_prioritizes_source(cached):
    current = {
        "reference_etag": "etag-b",
        "source_generation": "generation-2",
    }

    assert compare_metadata(cached, current) == "source_changed"
