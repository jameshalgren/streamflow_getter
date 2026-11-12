
"""Geographic selection of NWM reaches using channel geometries."""

import math
import numbers
from pathlib import Path


def validate_feature_id(value) -> int:
    """Validate an NWM feature ID without silently changing its value."""
    if (
        isinstance(value, (bool, str))
        or not isinstance(value, numbers.Integral)
    ):
        raise ValueError(
            f"NWM feature ID must be an integer: {value!r}"
        )

    feature_id = int(value)

    if feature_id <= 0:
        raise ValueError(
            f"NWM feature ID must be a positive integer: {value!r}"
        )

    return feature_id


def validate_hydrofabric_crs(
    hydrofabric_path,
    layer: str = "nwm_reaches_conus",
    expected_crs: str = "EPSG:4269",
) -> None:
    """Reject a hydrofabric layer with an unexpected CRS."""
    import pyogrio
    from pyproj import CRS

    info = pyogrio.read_info(
        hydrofabric_path,
        layer=layer,
    )

    actual = info.get("crs")

    if not actual:
        raise ValueError("Hydrofabric CRS is missing")

    if not CRS.from_user_input(actual).equals(
        CRS.from_user_input(expected_crs)
    ):
        raise ValueError(
            f"Unexpected hydrofabric CRS: {actual}; "
            f"expected {expected_crs}"
        )


def nearest_reaches(
    reaches,
    longitude: float,
    latitude: float,
    *,
    max_distance_m: float = 500,
    limit: int = 5,
    projected_crs: str = "EPSG:5070",
):
    """Find nearby NWM reaches using actual channel geometries.

    Parameters
    ----------
    reaches:
        GeoDataFrame containing 'ID' and channel geometries.
    longitude, latitude:
        Geographic coordinates in EPSG:4326.
    max_distance_m:
        Maximum search distance in projected meters.
    limit:
        Maximum number of candidates returned.
    projected_crs:
        Projected CRS used for distance calculations.

    Returns
    -------
    list[dict]
        Candidate feature IDs and distances, nearest first.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    if not (
        math.isfinite(longitude)
        and math.isfinite(latitude)
        and -180 <= longitude <= 180
        and -90 <= latitude <= 90
    ):
        raise ValueError("Invalid geographic coordinates")

    if not math.isfinite(max_distance_m) or max_distance_m <= 0:
        raise ValueError("max_distance_m must be positive")

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")

    if "ID" not in reaches.columns:
        raise ValueError("Reach geometries require an 'ID' column")

    if reaches.crs is None:
        raise ValueError("Reach geometries require a defined CRS")

    if reaches.empty:
        return []

    projected = reaches.to_crs(projected_crs)

    point = gpd.GeoSeries(
        [Point(longitude, latitude)],
        crs="EPSG:4326",
    ).to_crs(projected_crs).iloc[0]

    distances = projected.geometry.distance(point)

    candidates = []

    for position, distance in enumerate(distances):
        if not math.isfinite(distance):
            continue

        if distance <= max_distance_m:
            feature_id = validate_feature_id(
                projected.iloc[position]["ID"]
            )

            candidates.append({
                "feature_id": feature_id,
                "distance_m": float(distance),
            })

    candidates.sort(
        key=lambda item: (
            item["distance_m"],
            item["feature_id"],
        )
    )

    return candidates[:limit]


def load_nearby_reaches(
    hydrofabric_path,
    longitude: float,
    latitude: float,
    *,
    max_distance_m: float = 500,
    layer: str = "nwm_reaches_conus",
    projected_crs: str = "EPSG:5070",
):
    """Read CONUS channel geometries near a geographic point.

    Uses a conservative projected search envelope to retrieve
    candidate geometries. Exact distance filtering is performed
    separately by nearest_reaches().
    """
    import geopandas as gpd
    import pyogrio
    from shapely.geometry import Point

    path = Path(hydrofabric_path)

    if not path.exists():
        raise FileNotFoundError(f"Hydrofabric not found: {path}")

    if not (
        math.isfinite(longitude)
        and math.isfinite(latitude)
        and -180 <= longitude <= 180
        and -90 <= latitude <= 90
    ):
        raise ValueError("Invalid geographic coordinates")

    if not math.isfinite(max_distance_m) or max_distance_m <= 0:
        raise ValueError("max_distance_m must be positive")

    validate_hydrofabric_crs(path, layer=layer)

    point = gpd.GeoSeries(
        [Point(longitude, latitude)],
        crs="EPSG:4326",
    ).to_crs(projected_crs)

    # Construct a conservative search envelope in projected meters.
    # The margin reduces the risk of missing boundary candidates.
    envelope_margin_m = max(1.0, max_distance_m * 0.001)

    search_area = point.buffer(
        max_distance_m + envelope_margin_m,
        quad_segs=256,
    )

    # The verified CONUS hydrofabric uses EPSG:4269.
    envelope = search_area.to_crs("EPSG:4269").total_bounds

    reaches = pyogrio.read_dataframe(
        path,
        layer=layer,
        bbox=tuple(envelope),
        columns=["ID"],
    )

    return reaches


def _reaches_intersecting_geometry(
    hydrofabric_path,
    geometry,
    *,
    geometry_crs: str = "EPSG:4326",
    layer: str = "nwm_reaches_conus",
) -> list[int]:
    """Find CONUS NWM reaches intersecting a geographic geometry."""
    import geopandas as gpd
    import pyogrio
    from pyproj import CRS

    path = Path(hydrofabric_path)

    if not path.exists():
        raise FileNotFoundError(f"Hydrofabric not found: {path}")

    validate_hydrofabric_crs(path, layer=layer)

    # Transform the input geometry into the hydrofabric CRS.
    query = gpd.GeoSeries(
        [geometry],
        crs=geometry_crs,
    ).to_crs("EPSG:4269").iloc[0]

    # Read candidate geometries using their bounding boxes.
    reaches = pyogrio.read_dataframe(
        path,
        layer=layer,
        bbox=query.bounds,
        columns=["ID"],
    )

    if reaches.crs is None or not CRS.from_user_input(
        reaches.crs
    ).equals(CRS.from_epsg(4269)):
        raise ValueError(
            "Unexpected CRS in loaded reach geometries"
        )

    # Apply exact geometric intersection after candidate loading.
    selected = reaches[
        reaches.geometry.intersects(query)
    ]

    return sorted(
        {validate_feature_id(value) for value in selected["ID"]}
    )


def reaches_in_bbox(
    hydrofabric_path,
    bbox,
    *,
    layer: str = "nwm_reaches_conus",
):
    """Return NWM feature IDs intersecting a geographic bounding box.

    bbox is (west, south, east, north) in EPSG:4326.
    Currently supports CONUS and boxes not crossing the antimeridian.
    """
    from shapely.geometry import box

    if len(bbox) != 4:
        raise ValueError("bbox must contain four coordinates")

    west, south, east, north = bbox

    if not all(
        isinstance(value, (int, float)) and math.isfinite(value)
        for value in bbox
    ):
        raise ValueError("bbox coordinates must be finite numbers")

    if not (
        -180 <= west < east <= 180
        and -90 <= south < north <= 90
    ):
        raise ValueError("Invalid geographic bounding box")

    return _reaches_intersecting_geometry(
        hydrofabric_path,
        box(west, south, east, north),
        geometry_crs="EPSG:4326",
        layer=layer,
    )


def reaches_in_polygon(
    hydrofabric_path,
    polygon,
    *,
    layer: str = "nwm_reaches_conus",
    polygon_crs: str = "EPSG:4326",
):
    """Return NWM feature IDs intersecting a Polygon or MultiPolygon."""
    from shapely.geometry import MultiPolygon, Polygon

    if not isinstance(polygon, (Polygon, MultiPolygon)):
        raise ValueError("Expected a Polygon or MultiPolygon")

    if polygon.is_empty or not polygon.is_valid:
        raise ValueError("Polygon must be nonempty and valid")

    return _reaches_intersecting_geometry(
        hydrofabric_path,
        polygon,
        geometry_crs=polygon_crs,
        layer=layer,
    )



def load_geojson_polygon(path):
    """Load one valid Polygon or MultiPolygon from GeoJSON.

    Accepts a GeoJSON geometry, Feature, or FeatureCollection
    containing exactly one feature.

    Coordinates must be geographic longitude/latitude (EPSG:4326).
    """
    import json

    from shapely.geometry import MultiPolygon, Polygon, shape

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"GeoJSON file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("GeoJSON root must be an object")

    geojson_type = data.get("type")

    if geojson_type == "FeatureCollection":
        features = data.get("features")

        if not isinstance(features, list) or len(features) != 1:
            raise ValueError(
                "GeoJSON FeatureCollection must contain exactly one feature"
            )

        feature = features[0]

        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("Invalid GeoJSON feature")

        geometry_data = feature.get("geometry")

    elif geojson_type == "Feature":
        geometry_data = data.get("geometry")

    else:
        geometry_data = data

    if not isinstance(geometry_data, dict):
        raise ValueError("GeoJSON geometry must be an object")

    if geometry_data.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError(
            "GeoJSON geometry must be Polygon or MultiPolygon"
        )

    try:
        polygon = shape(geometry_data)
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise ValueError("Invalid GeoJSON polygon geometry") from exc

    if not isinstance(polygon, (Polygon, MultiPolygon)):
        raise ValueError("Expected Polygon or MultiPolygon")

    if polygon.is_empty or not polygon.is_valid:
        raise ValueError("Polygon must be nonempty and valid")

    # Validate geographic coordinate bounds for WGS84 input.
    minx, miny, maxx, maxy = polygon.bounds

    if not all(
        math.isfinite(value)
        for value in (minx, miny, maxx, maxy)
    ):
        raise ValueError(
            "GeoJSON coordinates must be finite"
        )

    if not (
        -180 <= minx <= maxx <= 180
        and -90 <= miny <= maxy <= 90
    ):
        raise ValueError(
            "GeoJSON coordinates must be valid longitude/latitude"
        )

    return polygon
