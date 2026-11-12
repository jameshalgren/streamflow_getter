"""Command-line interface for streamflow_getter."""

import argparse
import math
from pathlib import Path

from streamflow_getter import __version__, nwm


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="streamflow-getter",
        description="Download streamflow time series for specific reaches.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
    )

    sub = parser.add_subparsers(dest="source")

    # Preserve the existing retrospective command.
    p = sub.add_parser(
        "nwm",
        help="NWM retrospective streamflow (CONUS; coverage varies by version)",
    )
    p.add_argument(
        "--reach",
        type=int,
        action="append",
        default=[],
        help="feature_id (COMID); repeat for several",
    )
    p.add_argument(
        "--gage",
        action="append",
        default=[],
        help="USGS gage ID, e.g. 01646500; repeat for several",
    )
    p.add_argument(
        "--version",
        dest="nwm_version",
        choices=["3.0", "2.1"],
        default="3.0",
        help="retrospective version (3.0 ends 2023-02, 2.1 ends 2020-12)",
    )
    p.add_argument("--start", required=True, help="e.g. 2020-01-01")
    p.add_argument("--end", required=True, help="e.g. 2020-01-31")
    p.add_argument("--variable", default="streamflow")
    p.add_argument("--out", required=True, help="output CSV path")

    # Operational NWM short-range CONUS retrieval.

    operational = sub.add_parser(
        "nwm-operational",
        help="Operational NWM CONUS forecasts",
    )
    date_selection = operational.add_mutually_exclusive_group(
        required=True
    )
    date_selection.add_argument(
        "--date",
        help="Single forecast initialization date (YYYY-MM-DD)",
    )
    date_selection.add_argument(
        "--start-date",
        help="Inclusive UTC start date (YYYY-MM-DD)",
    )
    date_selection.add_argument(
        "--recent-days",
        type=int,
        metavar="N",
        help=(
            "Most recent N UTC calendar dates, including "
            "the current UTC date"
        ),
    )
    operational.add_argument(
        "--end-date",
        help="Inclusive UTC end date; requires --start-date",
    )
    operational.add_argument("--cycle", type=int, default=0)

    operational.add_argument(
        "--product",
        choices=[
            "short_range",
            "medium_range_mem1",
            "medium_range_mem2",
            "medium_range_mem3",
            "medium_range_mem4",
            "medium_range_mem5",
            "medium_range_mem6",
            "medium_range_blend",
            "medium_range_no_da",
            "long_range_mem1",
            "long_range_mem2",
            "long_range_mem3",
            "long_range_mem4",
        ],
        default="short_range",
        help="Operational NWM product (default: short_range)",
    )

    operational.add_argument(
        "--reach",
        type=int,
        action="append",
        default=[],
        help="NWM feature ID; repeat for several reaches",
    )
    operational.add_argument(
        "--gage",
        action="append",
        default=[],
        help="USGS gage ID; preserve leading zeros",
    )
    operational.add_argument(
        "--routelink",
        help="Path to local RouteLink NetCDF for gage resolution",
    )
    operational.add_argument(
        "--point",
        type=float,
        nargs=2,
        metavar=("LONGITUDE", "LATITUDE"),
        help="Select the nearest NWM channel to a geographic point",
    )
    operational.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help="Select NWM reaches intersecting a geographic bounding box",
    )

    operational.add_argument(
        "--polygon",
        metavar="GEOJSON_PATH",
        help="Select NWM reaches intersecting a GeoJSON Polygon or MultiPolygon",
    )

    operational.add_argument(
        "--hydrofabric",
        help="Path to the NWM channel hydrofabric geodatabase",
    )
    operational.add_argument(
        "--max-distance-m",
        type=float,
        default=500.0,
        help="Maximum point-to-channel distance in meters (default: 500)",
    )
    operational.add_argument(
        "--max-reaches",
        type=int,
        default=100,
        help="Maximum reaches allowed per operational request (default: 100)",
    )
    operational.add_argument(
        "--start-hour",
        type=int,
        default=1,
    )
    operational.add_argument(
        "--end-hour",
        type=int,
        default=18,
    )
    operational.add_argument(
        "--no-t0",
        action="store_true",
        help="Exclude analysis_assim t0",
    )
    cache_policy = operational.add_mutually_exclusive_group()
    cache_policy.add_argument(
        "--cache-dir",
        default="~/.cache/streamflow_getter",
        metavar="PATH",
        help=(
            "Kerchunk reference cache directory "
            "(default: ~/.cache/streamflow_getter)"
        ),
    )
    cache_policy.add_argument(
        "--no-cache",
        dest="cache_dir",
        action="store_const",
        const=None,
        help="Disable persistent Kerchunk reference caching",
    )
    operational.add_argument(
        "--format",
        choices=["csv", "parquet"],
        dest="output_format",
    )
    operational.add_argument("--out", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.source == "nwm":
        if not (args.reach or args.gage):
            parser.error("nwm needs at least one --reach or --gage")

        ds = nwm.open_chrtout(args.nwm_version)
        reaches = list(args.reach) + list(
            nwm.gages_to_reaches(args.gage, ds).values()
        )

        df = nwm.fetch(
            reaches,
            args.start,
            args.end,
            args.variable,
            ds=ds,
        )
        df.to_csv(args.out, index=False)
        print(f"wrote {len(df)} rows to {args.out}")
        return 0

    if args.source == "nwm-operational":
        # Import operational dependencies only when requested.
        from streamflow_getter.operational_nwm import (
            ForecastConfig,
            fetch_operational_series,
        )
        from streamflow_getter.operational_requests import (
            fetch_operational_configs,
        )
        from streamflow_getter.request_planning import (
            plan_operational_configs,
            resolve_recent_date_range,
        )
        from streamflow_getter.output import (
            manifest_path_for,
            resolve_output_format,
            write_timeseries_with_manifest,
        )
        from streamflow_getter.operational_provenance import (
            build_operational_run_manifest,
        )


        if args.date is not None:
            if args.end_date is not None:
                raise ValueError(
                    "--end-date cannot be used with --date"
                )

            configs = [
                ForecastConfig(
                    date=args.date,
                    cycle=args.cycle,
                    product=args.product,
                )
            ]

            temporal_selection = {
                "mode": "single_date",
                "requested_date": args.date,
                "resolved_start_date": args.date,
                "resolved_end_date": args.date,
            }

        elif args.start_date is not None:
            if args.end_date is None:
                raise ValueError(
                    "--end-date is required with --start-date"
                )

            configs = plan_operational_configs(
                args.start_date,
                args.end_date,
                cycles=(args.cycle,),
                products=(args.product,),
            )

            temporal_selection = {
                "mode": "explicit_period",
                "requested_start_date": args.start_date,
                "requested_end_date": args.end_date,
                "resolved_start_date": args.start_date,
                "resolved_end_date": args.end_date,
            }

        else:
            if args.end_date is not None:
                raise ValueError(
                    "--end-date requires --start-date"
                )

            recent_start, recent_end = (
                resolve_recent_date_range(
                    args.recent_days
                )
            )

            print(
                f"Resolved --recent-days {args.recent_days} "
                f"to UTC dates {recent_start} through "
                f"{recent_end}"
            )

            configs = plan_operational_configs(
                recent_start,
                recent_end,
                cycles=(args.cycle,),
                products=(args.product,),
            )

            temporal_selection = {
                "mode": "recent_days",
                "requested_days": args.recent_days,
                "resolved_start_date": recent_start,
                "resolved_end_date": recent_end,
            }


        # Reject invalid forecast-hour ranges before remote access.
        if args.start_hour < 1 or args.end_hour < args.start_hour:
            raise ValueError(
                "Invalid forecast hour range: start_hour must be "
                "positive and end_hour must not precede start_hour"
            )


        # Validate product-specific forecast hours before remote access.
        for config in configs:
            config.forecast_hours(
                args.start_hour,
                args.end_hour,
            )


        # Validate data and manifest destinations before remote retrieval.
        resolved_output_format = resolve_output_format(
            args.out,
            args.output_format,
        )

        destination_path = Path(
            args.out
        ).expanduser()

        manifest_destination_path = manifest_path_for(
            destination_path
        )

        if destination_path.exists():
            raise FileExistsError(
                f"Output already exists: {destination_path}"
            )

        if manifest_destination_path.exists():
            raise FileExistsError(
                f"Manifest already exists: {manifest_destination_path}"
            )

        # Validate reach-selection arguments before remote NWM access.
        if not (
            args.reach or args.gage or args.point
            or args.bbox or args.polygon
        ):
            raise ValueError(
                "Provide at least one --reach, --gage, "
                "--point, --bbox, or --polygon"
            )

        if (
            args.point or args.bbox or args.polygon
        ) and not args.hydrofabric:
            raise ValueError(
                "--hydrofabric is required for geographic selection"
            )

        if args.point and (
            not math.isfinite(args.max_distance_m)
            or args.max_distance_m <= 0
        ):
            raise ValueError(
                "max_distance_m must be positive and finite"
            )

        if args.hydrofabric and not (
            args.point or args.bbox or args.polygon
        ):
            raise ValueError(
                "--hydrofabric requires --point, --bbox, or --polygon"
            )

        if args.max_reaches < 1:
            raise ValueError(
                "max_reaches must be a positive integer"
            )

        if args.gage and not args.routelink:
            raise ValueError(
                "--routelink is required when using --gage"
            )

        if args.routelink and not args.gage:
            raise ValueError(
                "--routelink requires at least one --gage"
            )

        reaches = list(args.reach)
        routelink_selection = None

        # Resolve geographic bounding-box selections locally.
        if args.bbox:
            from streamflow_getter.spatial_resolution import reaches_in_bbox

            selected_reaches = reaches_in_bbox(
                args.hydrofabric,
                tuple(args.bbox),
            )

            if not selected_reaches:
                raise ValueError(
                    "No NWM reaches found within the bounding box"
                )

            if len(selected_reaches) > args.max_reaches:
                raise ValueError(
                    f"Bounding box selected {len(selected_reaches)} reaches; "
                    f"maximum allowed is {args.max_reaches}"
                )

            reaches.extend(selected_reaches)

            print(
                f"Selected {len(selected_reaches)} NWM reaches "
                "from geographic bounding box"
            )



        # Resolve GeoJSON polygon selections locally.
        if args.polygon:
            from streamflow_getter.spatial_resolution import (
                load_geojson_polygon,
                reaches_in_polygon,
            )

            polygon = load_geojson_polygon(args.polygon)

            selected_reaches = reaches_in_polygon(
                args.hydrofabric,
                polygon,
            )

            if not selected_reaches:
                raise ValueError(
                    "No NWM reaches found within the polygon"
                )

            if len(selected_reaches) > args.max_reaches:
                raise ValueError(
                    f"Polygon selected {len(selected_reaches)} reaches; "
                    f"maximum allowed is {args.max_reaches}"
                )

            reaches.extend(selected_reaches)

            print(
                f"Selected {len(selected_reaches)} NWM reaches "
                "from GeoJSON polygon"
            )



        # Resolve the nearest NWM channel to a geographic point.
        if args.point:
            from streamflow_getter.spatial_resolution import (
                load_nearby_reaches,
                nearest_reaches,
            )

            longitude, latitude = args.point

            nearby = load_nearby_reaches(
                args.hydrofabric,
                longitude,
                latitude,
                max_distance_m=args.max_distance_m,
            )

            candidates = nearest_reaches(
                nearby,
                longitude,
                latitude,
                max_distance_m=args.max_distance_m,
                limit=1,
            )

            if not candidates:
                raise ValueError(
                    "No NWM reaches found within the maximum distance"
                )

            selected = candidates[0]
            reaches.append(selected["feature_id"])

            print(
                f"Selected NWM reach {selected['feature_id']} "
                f"at {selected['distance_m']:.2f} m"
            )

        # Resolve USGS gages through the local RouteLink index.
        if args.gage:
            from streamflow_getter.operational_versions import (
                resolve_operational_nwm_version,
            )
            from streamflow_getter.reach_resolution import (
                classify_gage_index_version,
                load_gage_index,
                resolve_gages,
                validate_routelink_compatibility,
            )

            index = load_gage_index(
                args.routelink
            )

            routelink_provenance = (
                classify_gage_index_version(
                    index
                )
            )

            request_versions = [
                resolve_operational_nwm_version(
                    config
                )
                for config in configs
            ]

            compatibility = (
                validate_routelink_compatibility(
                    request_versions,
                    routelink_provenance[
                        "network_version"
                    ],
                )
            )

            resolved = resolve_gages(
                args.gage,
                index,
            )

            reaches.extend(
                resolved.values()
            )

            resolved_versions = sorted({
                version
                for version in request_versions
                if version is not None
            })

            routelink_selection = {
                "gage_resolution": {
                    "gage_ids": list(
                        args.gage
                    ),
                    "resolved_gages": dict(
                        resolved
                    ),
                    "routelink": {
                        "file_name": Path(
                            args.routelink
                        ).expanduser().name,
                        "crosswalk_sha256":
                            routelink_provenance[
                                "crosswalk_sha256"
                            ],
                        "network_version":
                            routelink_provenance[
                                "network_version"
                            ],
                        "gage_count":
                            routelink_provenance[
                                "gage_count"
                            ],
                        "compatibility":
                            compatibility,
                        "requested_nwm_versions":
                            resolved_versions,
                        "unresolved_request_version_count":
                            sum(
                                version is None
                                for version
                                in request_versions
                            ),
                    },
                },
            }

        # Validate the combined reach selection.
        if any(reach <= 0 for reach in reaches):
            raise ValueError(
                "Reach IDs must be positive integers"
            )

        if len(reaches) != len(set(reaches)):
            raise ValueError(
                "Duplicate NWM feature IDs are not allowed"
            )

        if (args.bbox or args.polygon) and len(reaches) > args.max_reaches:
            raise ValueError(
                f"Request contains {len(reaches)} reaches; "
                f"maximum allowed is {args.max_reaches}"
            )

        # Retrieve operational NWM streamflow after local validation.
        if args.date is not None:
            single_frame = fetch_operational_series(
                configs[0],
                reaches,
                args.start_hour,
                args.end_hour,
                include_t0=not args.no_t0,
                cache_dir=args.cache_dir,
            )

            manifest_frame = single_frame.copy()

            if "requested_product" in manifest_frame.columns:
                raise ValueError(
                    "Single-date operational result unexpectedly "
                    "contains requested_product"
                )

            manifest_frame.insert(
                2,
                "requested_product",
                args.product,
            )

        else:
            manifest_frame = fetch_operational_configs(
                configs,
                reaches,
                args.start_hour,
                args.end_hour,
                include_t0=not args.no_t0,
                cache_dir=args.cache_dir,
            )

            if (
                "requested_product" not in manifest_frame.columns
                or not manifest_frame["requested_product"].eq(
                    args.product
                ).all()
            ):
                raise ValueError(
                    "Unexpected requested product in "
                    "planned operational result"
                )

        if args.cache_dir is None:
            cache_policy = {
                "mode": "disabled",
            }
        else:
            cache_policy = {
                "mode": "persistent",
                "directory": args.cache_dir,
            }

        try:
            from importlib.metadata import version

            package_version = version(
                "streamflow-getter"
            )
        except Exception:
            package_version = "unknown"

        manifest_selection = {
            "temporal": temporal_selection,
        }

        if routelink_selection is not None:
            manifest_selection[
                "spatial"
            ] = routelink_selection

        manifest = build_operational_run_manifest(
            manifest_frame,
            configs,
            reaches,
            args.start_hour,
            args.end_hour,
            include_t0=not args.no_t0,
            selection=manifest_selection,
            cache_policy=cache_policy,
            software={
                "streamflow_getter_version": package_version,
            },
            diagnostics={
                "execution_mode": "strict",
            },
        )

        # Preserve the established one-product CLI data schema.
        frame = manifest_frame.drop(
            columns=["requested_product"]
        )

        destination, manifest_destination = (
            write_timeseries_with_manifest(
                frame,
                args.out,
                manifest,
                output_format=resolved_output_format,
                manifest_path=manifest_destination_path,
            )
        )

        print(
            f"wrote {len(frame)} rows to {destination}"
        )
        print(
            f"wrote run manifest to {manifest_destination}"
        )

        return 0

    return 0
