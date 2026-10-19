import argparse

from streamflow_getter import __version__, nwm


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="streamflow-getter",
        description="Download streamflow time series for specific reaches.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="source")

    p = sub.add_parser("nwm", help="NWM retrospective, CONUS (hourly, 1979-)")
    p.add_argument("--reach", type=int, action="append", default=[],
                   help="feature_id (COMID); repeat for several")
    p.add_argument("--gage", action="append", default=[],
                   help="USGS gage ID, e.g. 01646500; repeat for several")
    p.add_argument("--version", dest="nwm_version", choices=["3.0", "2.1"],
                   default="3.0", help="retrospective version (3.0 ends 2023-02, 2.1 ends 2020-12)")
    p.add_argument("--start", required=True, help="e.g. 2020-01-01")
    p.add_argument("--end", required=True, help="e.g. 2020-01-31")
    p.add_argument("--variable", default="streamflow")
    p.add_argument("--out", required=True, help="output CSV path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.source == "nwm":
        if not (args.reach or args.gage):
            build_parser().error("nwm needs at least one --reach or --gage")
        ds = nwm.open_chrtout(args.nwm_version)
        reaches = list(args.reach) + list(nwm.gages_to_reaches(args.gage, ds).values())
        df = nwm.fetch(reaches, args.start, args.end, args.variable, ds=ds)
        df.to_csv(args.out, index=False)
        print(f"wrote {len(df)} rows to {args.out}")
    return 0
