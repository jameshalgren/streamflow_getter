"""Tests for operational RouteLink reach resolution."""

import numpy as np
import pytest
import xarray as xr

from streamflow_getter.reach_resolution import (
    build_gage_index,
    resolve_gages,
)


@pytest.fixture
def routelink():
    return xr.Dataset(
        {
            "link": ("feature_id", [3586192, 1122645, 7144704]),
            "gages": (
                "feature_id",
                np.array([b"08165500", b"01646500", b""]),
            ),
        }
    )


def test_build_gage_index(routelink):
    assert build_gage_index(routelink) == {
        "08165500": 3586192,
        "01646500": 1122645,
    }


def test_resolve_gages(routelink):
    index = build_gage_index(routelink)

    assert resolve_gages(["08165500"], index) == {
        "08165500": 3586192
    }


def test_unknown_gage(routelink):
    index = build_gage_index(routelink)

    with pytest.raises(ValueError, match="not found"):
        resolve_gages(["99999999"], index)


def test_duplicate_feature_ids():
    ds = xr.Dataset(
        {
            "link": ("feature_id", [3586192, 3586192]),
            "gages": ("feature_id", [b"08165500", b"01234567"]),
        }
    )

    with pytest.raises(ValueError, match="Duplicate"):
        build_gage_index(ds)


def test_ambiguous_gage():
    ds = xr.Dataset(
        {
            "link": ("feature_id", [3586192, 1122645]),
            "gages": ("feature_id", [b"08165500", b"08165500"]),
        }
    )

    with pytest.raises(ValueError, match="Ambiguous"):
        build_gage_index(ds)



def test_seven_digit_gage_exact_match():
    index = {
        "1234567": 101,
        "01234567": 181,
    }

    assert resolve_gages(["1234567"], index) == {
        "1234567": 101
    }

    assert resolve_gages(["01234567"], index) == {
        "01234567": 181
    }


def test_no_automatic_zero_padding():
    index = {"01234567": 181}

    with pytest.raises(ValueError, match="not found"):
        resolve_gages(["1234567"], index)


def test_nonnumeric_gage_preserved():
    index = {"08AB123": 500}

    assert resolve_gages(["08AB123"], index) == {
        "08AB123": 500
    }




def test_load_gage_index(tmp_path, monkeypatch):
    """Load RouteLink through xarray without a NetCDF backend."""
    from unittest.mock import MagicMock

    from streamflow_getter.reach_resolution import load_gage_index

    path = tmp_path / "routelink.nc"
    path.touch()

    ds = xr.Dataset({
        "link": ("feature_id", [3586192, 1122645]),
        "gages": (
            "feature_id",
            [b"08165500", b"01646500"],
        ),
    })

    context = MagicMock()
    context.__enter__.return_value = ds

    mocked_open = MagicMock(return_value=context)

    monkeypatch.setattr(
        "streamflow_getter.reach_resolution.xr.open_dataset",
        mocked_open,
    )

    result = load_gage_index(path, engine="h5netcdf")

    assert result == {
        "08165500": 3586192,
        "01646500": 1122645,
    }

    mocked_open.assert_called_once_with(
        path,
        engine="h5netcdf",
    )

    context.__exit__.assert_called_once()



def test_load_gage_index_missing_file(tmp_path):
    from streamflow_getter.reach_resolution import load_gage_index

    with pytest.raises(FileNotFoundError, match="not found"):
        load_gage_index(tmp_path / "missing.nc")


def test_reject_noninteger_feature_ids():
    ds = xr.Dataset({
        "link": ("feature_id", [3586192.5, 1122645.0]),
        "gages": ("feature_id", [b"08165500", b"01646500"]),
    })

    with pytest.raises(ValueError, match="integer"):
        build_gage_index(ds)

def test_canonical_gage_index_sha256_is_order_independent():
    import hashlib

    from streamflow_getter.reach_resolution import (
        canonical_gage_index_sha256,
    )

    first = {
        "08165500": 3586192,
        "01646500": 1122645,
    }

    second = {
        "01646500": 1122645,
        "08165500": 3586192,
    }

    expected_payload = (
        "01646500\t1122645\n"
        "08165500\t3586192\n"
    ).encode("utf-8")

    expected = hashlib.sha256(
        expected_payload
    ).hexdigest()

    assert canonical_gage_index_sha256(
        first
    ) == expected

    assert canonical_gage_index_sha256(
        second
    ) == expected


def test_canonical_gage_index_sha256_validates_values():
    from streamflow_getter.reach_resolution import (
        canonical_gage_index_sha256,
    )

    with pytest.raises(
        ValueError,
        match="nonempty strings",
    ):
        canonical_gage_index_sha256({
            "": 101,
        })

    with pytest.raises(
        ValueError,
        match="positive integers",
    ):
        canonical_gage_index_sha256({
            "08165500": 0,
        })

    with pytest.raises(
        TypeError,
        match="dictionary",
    ):
        canonical_gage_index_sha256(
            []
        )


@pytest.mark.parametrize(
    "digest,expected",
    [
        (
            "3e4232517ce3958bebfa7d9d66826f8e"
            "e59c34f0b5b90fb540c3d4ab159d2c68",
            "3.0",
        ),
        (
            "c0ee33504fd74319e68ba07b370110d0"
            "22efe09a76a022ccb7361921fc909ec6",
            "3.1",
        ),
        (
            "0" * 64,
            None,
        ),
    ],
)
def test_known_routelink_crosswalk_hashes(
    digest,
    expected,
):
    from streamflow_getter.reach_resolution import (
        classify_routelink_crosswalk_sha256,
    )

    assert classify_routelink_crosswalk_sha256(
        digest
    ) == expected


def test_routelink_crosswalk_hash_rejects_invalid_digest():
    from streamflow_getter.reach_resolution import (
        classify_routelink_crosswalk_sha256,
    )

    with pytest.raises(
        ValueError,
        match="SHA256",
    ):
        classify_routelink_crosswalk_sha256(
            "not-a-sha"
        )


def test_classify_small_unknown_gage_index():
    from streamflow_getter.reach_resolution import (
        canonical_gage_index_sha256,
        classify_gage_index_version,
    )

    index = {
        "08165500": 3586192,
        "01646500": 1122645,
    }

    result = classify_gage_index_version(
        index
    )

    assert result == {
        "crosswalk_sha256":
            canonical_gage_index_sha256(
                index
            ),
        "network_version": None,
        "gage_count": 2,
    }


def test_load_gage_index_with_provenance(
    tmp_path,
    monkeypatch,
):
    from unittest.mock import MagicMock

    from streamflow_getter.reach_resolution import (
        canonical_gage_index_sha256,
        load_gage_index_with_provenance,
    )

    path = (
        tmp_path
        / "RouteLink_CONUS.nc"
    )

    path.touch()

    ds = xr.Dataset({
        "link": (
            "feature_id",
            [3586192, 1122645],
        ),
        "gages": (
            "feature_id",
            [
                b"08165500",
                b"01646500",
            ],
        ),
    })

    context = MagicMock()
    context.__enter__.return_value = ds

    mocked_open = MagicMock(
        return_value=context
    )

    monkeypatch.setattr(
        "streamflow_getter.reach_resolution.xr.open_dataset",
        mocked_open,
    )

    index, provenance = (
        load_gage_index_with_provenance(
            path,
            engine="h5netcdf",
        )
    )

    assert index == {
        "08165500": 3586192,
        "01646500": 1122645,
    }

    assert provenance == {
        "crosswalk_sha256":
            canonical_gage_index_sha256(
                index
            ),
        "network_version": None,
        "gage_count": 2,
    }

    mocked_open.assert_called_once_with(
        path,
        engine="h5netcdf",
    )

    context.__exit__.assert_called_once()


def test_routelink_compatibility_matching_version():
    from streamflow_getter.reach_resolution import (
        validate_routelink_compatibility,
    )

    assert validate_routelink_compatibility(
        ["3.1", "3.1"],
        "3.1",
    ) == "compatible"


def test_routelink_compatibility_rejects_known_mismatch():
    from streamflow_getter.reach_resolution import (
        validate_routelink_compatibility,
    )

    with pytest.raises(
        ValueError,
        match="incompatible",
    ):
        validate_routelink_compatibility(
            ["3.0"],
            "3.1",
        )

    with pytest.raises(
        ValueError,
        match="3.0, 3.1",
    ):
        validate_routelink_compatibility(
            ["3.0", "3.1"],
            "3.1",
        )


def test_routelink_compatibility_allows_unknown_asset():
    from streamflow_getter.reach_resolution import (
        validate_routelink_compatibility,
    )

    assert validate_routelink_compatibility(
        ["3.1"],
        None,
    ) == "unknown_routelink_version"


def test_routelink_compatibility_tracks_unresolved_request():
    from streamflow_getter.reach_resolution import (
        validate_routelink_compatibility,
    )

    assert validate_routelink_compatibility(
        ["3.1", None],
        "3.1",
    ) == "unresolved_request_version"
