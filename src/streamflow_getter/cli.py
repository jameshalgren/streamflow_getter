import argparse

from streamflow_getter import __version__, nwm


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="streamflow-getter",
        description="Download streamflow time series for specific reaches.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="source")

    p = sub.add_parser("nwm", help="NWM v3.0 retrospective, CONUS (1979-2023)")
    p.add_argument("--reach", type=int, action="append", required=True,
                   help="feature_id (COMID); repeat for several")
    p.add_argument("--start", required=True, help="e.g. 2020-01-01")
    p.add_argument("--end", required=True, help="e.g. 2020-01-31")
    p.add_argument("--variable", default="streamflow")
    p.add_argument("--out", required=True, help="output CSV path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.source == "nwm":
        df = nwm.fetch(args.reach, args.start, args.end, args.variable)
        df.to_csv(args.out, index=False)
        print(f"wrote {len(df)} rows to {args.out}")
    return 0
