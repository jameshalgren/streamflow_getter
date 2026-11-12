"""Resolve operational NWM reaches using RouteLink metadata."""

from collections import defaultdict

import numpy as np
import xarray as xr


def build_gage_index(ds: xr.Dataset) -> dict[str, int]:
    """Build a validated gage-to-feature-ID index from RouteLink."""
    if "link" not in ds or "gages" not in ds:
        raise ValueError("RouteLink requires 'link' and 'gages'")

    links = np.asarray(ds["link"].values)
    gages = np.asarray(ds["gages"].values)

    if not np.issubdtype(links.dtype, np.integer):
        raise ValueError("RouteLink feature IDs must be integers")

    if links.ndim != 1 or gages.ndim != 1:
        raise ValueError("RouteLink identifiers must be one-dimensional")

    if len(links) != len(gages):
        raise ValueError("RouteLink link/gages length mismatch")

    if len(np.unique(links)) != len(links):
        raise ValueError("Duplicate RouteLink feature IDs")

    mapping = defaultdict(set)

    for link, raw_gage in zip(links, gages):
        if isinstance(raw_gage, bytes):
            gage = raw_gage.decode("utf-8").strip()
        else:
            gage = str(raw_gage).strip()

        if gage:
            mapping[gage].add(int(link))

    ambiguous = {
        gage: reaches
        for gage, reaches in mapping.items()
        if len(reaches) > 1
    }

    if ambiguous:
        raise ValueError(
            f"Ambiguous RouteLink gage mappings: {len(ambiguous)}"
        )

    return {
        gage: next(iter(reaches))
        for gage, reaches in mapping.items()
    }



def resolve_gages(
    gages: list[str],
    index: dict[str, int],
) -> dict[str, int]:
    """Resolve gage IDs using exact string matching."""
    result = {}

    for gage in gages:
        if not isinstance(gage, str) or not gage:
            raise ValueError("Gage IDs must be nonempty strings")

        if gage not in index:
            raise ValueError(f"Gage not found in RouteLink: {gage}")

        result[gage] = index[gage]

    return result



def load_gage_index(
    path,
    *,
    engine=None,
) -> dict[str, int]:
    """Load and validate a RouteLink gage index from a NetCDF file."""
    from pathlib import Path

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"RouteLink file not found: {path}")

    with xr.open_dataset(path, engine=engine) as ds:
        return build_gage_index(ds)

# Canonical complete gage-to-reach crosswalk fingerprints derived from
# published HydroShare RouteLink conversions:
#
# NWM v3.0.17:
#   https://www.hydroshare.org/resource/
#   1fe9975004ce4b5097d41939afa14f84/
#
# NWM v3.1.6:
#   https://www.hydroshare.org/resource/
#   7829f98541134532b1b35f19d3d883bf/
#
# These fingerprints represent the complete validated CONUS gage-to-NWM
# feature crosswalk. They are not hashes of NetCDF bytes, filenames,
# metadata, or selected example gauges.
ROUTELINK_CROSSWALK_SHA256 = {
    "3.0": (
        "3e4232517ce3958bebfa7d9d66826f8e"
        "e59c34f0b5b90fb540c3d4ab159d2c68"
    ),
    "3.1": (
        "c0ee33504fd74319e68ba07b370110d0"
        "22efe09a76a022ccb7361921fc909ec6"
    ),
}


def canonical_gage_index_sha256(
    index: dict[str, int],
) -> str:
    """Hash a complete gage-to-feature index deterministically.

    The representation is independent of RouteLink row ordering,
    NetCDF string padding, source filename, and serialization format.
    """
    import hashlib
    import numbers

    if not isinstance(
        index,
        dict,
    ):
        raise TypeError(
            "RouteLink gage index must be a dictionary"
        )

    pieces = []

    for gage in sorted(index):
        reach = index[gage]

        if (
            not isinstance(gage, str)
            or not gage
        ):
            raise ValueError(
                "RouteLink gage IDs must be nonempty strings"
            )

        if (
            isinstance(reach, bool)
            or not isinstance(
                reach,
                numbers.Integral,
            )
            or int(reach) <= 0
        ):
            raise ValueError(
                "RouteLink feature IDs must be positive integers"
            )

        pieces.append(
            f"{gage}\t{int(reach)}\n"
        )

    payload = "".join(
        pieces
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        payload
    ).hexdigest()


def classify_routelink_crosswalk_sha256(
    digest: str,
) -> str | None:
    """Return the known operational network version for a crosswalk hash."""
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(
            character not in "0123456789abcdef"
            for character in digest.lower()
        )
    ):
        raise ValueError(
            "RouteLink crosswalk SHA256 must be a 64-character hex string"
        )

    normalized = digest.lower()

    for version, known_digest in (
        ROUTELINK_CROSSWALK_SHA256.items()
    ):
        if normalized == known_digest:
            return version

    return None


def classify_gage_index_version(
    index: dict[str, int],
) -> dict:
    """Classify one complete RouteLink crosswalk by canonical content."""
    digest = canonical_gage_index_sha256(
        index
    )

    return {
        "crosswalk_sha256": digest,
        "network_version":
            classify_routelink_crosswalk_sha256(
                digest
            ),
        "gage_count": len(index),
    }


def load_gage_index_with_provenance(
    path,
    *,
    engine=None,
) -> tuple[dict[str, int], dict]:
    """Load one RouteLink index plus content-based version provenance."""
    from pathlib import Path

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(
            f"RouteLink file not found: {path}"
        )

    with xr.open_dataset(
        path,
        engine=engine,
    ) as ds:
        index = build_gage_index(
            ds
        )

    provenance = (
        classify_gage_index_version(
            index
        )
    )

    return (
        index,
        provenance,
    )


def validate_routelink_compatibility(
    request_versions,
    routelink_version: str | None,
) -> str:
    """Validate a known RouteLink version against requested NWM versions.

    Known mismatches are rejected. Unknown RouteLink classification is
    allowed for backward compatibility but remains explicitly unverified.
    """
    versions = list(
        request_versions
    )

    for version in versions:
        if (
            version is not None
            and (
                not isinstance(version, str)
                or not version
            )
        ):
            raise ValueError(
                "Requested NWM versions must be strings or None"
            )

    if (
        routelink_version is not None
        and routelink_version
        not in ROUTELINK_CROSSWALK_SHA256
    ):
        raise ValueError(
            "Unknown classified RouteLink network version: "
            f"{routelink_version}"
        )

    resolved_versions = sorted({
        version
        for version in versions
        if version is not None
    })

    if routelink_version is None:
        return "unknown_routelink_version"

    incompatible = [
        version
        for version in resolved_versions
        if version != routelink_version
    ]

    if incompatible:
        requested = ", ".join(
            resolved_versions
        )

        raise ValueError(
            "RouteLink network version "
            f"{routelink_version} is incompatible with "
            f"requested NWM version(s): {requested}"
        )

    if any(
        version is None
        for version in versions
    ):
        return "unresolved_request_version"

    return "compatible"
