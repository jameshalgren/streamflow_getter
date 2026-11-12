"""Compare native remote retrieval across process boundaries."""

import argparse
import csv
import statistics
import subprocess
import sys
import time
from pathlib import Path

from repeated_benchmark import read_native_remote

HOUR = 1
INDEX = 351819
EXPECTED_FLOW = 0.40999999083578587
RESULTS = Path("benchmarks/results/cache_experiment.csv")


def retrieve():
    start = time.perf_counter()

    flow, valid_time, reference_time, requests, byte_count = (
        read_native_remote(HOUR, INDEX)
    )

    elapsed = time.perf_counter() - start

    if abs(flow - EXPECTED_FLOW) > 1e-6:
        raise ValueError(f"Unexpected streamflow: {flow}")

    return {
        "elapsed_seconds": elapsed,
        "streamflow_m3s": flow,
        "http_requests": requests,
        "response_body_bytes": byte_count,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["same", "separate"], required=True)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()

    if args.trials < 1:
        parser.error("--trials must be at least 1")

    if args.worker:
        print(
            ",".join(str(value) for value in retrieve().values())
        )
        return

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    records = []

    for trial in range(1, args.trials + 1):
        if args.mode == "same":
            result = retrieve()
        else:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--mode", "separate",
                    "--worker",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            values = completed.stdout.strip().split(",")
            if len(values) != 4:
                raise RuntimeError(
                    f"Unexpected worker output: {completed.stdout}"
                )

            result = {
                "elapsed_seconds": float(values[0]),
                "streamflow_m3s": float(values[1]),
                "http_requests": int(values[2]),
                "response_body_bytes": int(values[3]),
            }

        records.append({
            "mode": args.mode,
            "trial": trial,
            **result,
        })

        print(
            f"{args.mode:8} trial={trial} "
            f"time={result['elapsed_seconds']:.3f}s "
            f"bytes={result['response_body_bytes']}"
        )

    with RESULTS.open("a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0]))
        if file.tell() == 0:
            writer.writeheader()
        writer.writerows(records)

    print(
        f"\nMedian: "
        f"{statistics.median(r['elapsed_seconds'] for r in records):.3f}s"
    )
    print("Saved:", RESULTS)


if __name__ == "__main__":
    main()
