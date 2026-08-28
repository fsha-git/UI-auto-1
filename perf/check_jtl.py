"""Threshold gate for JMeter JTL (CSV) result files.

Reads a JTL, prints a summary, and exits non-zero when any threshold is
breached — so perf/run_perf.sh can fail a run on error rate / latency.
Named check_* (not test_*) on purpose so pytest never collects it.
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def percentile(sorted_values: list[int], pct: float) -> int:
    if not sorted_values:
        return 0
    idx = min(len(sorted_values) - 1, max(0, round(pct / 100 * len(sorted_values)) - 1))
    return sorted_values[idx]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jtl", help="path to results.jtl (CSV format)")
    parser.add_argument("--max-error-rate", type=float, default=None, help="max error rate in percent")
    parser.add_argument("--max-p95", type=int, default=None, help="max p95 latency in ms")
    parser.add_argument("--max-5xx", type=int, default=None, help="max number of 5xx responses")
    parser.add_argument("--json", default=None, help="also write metrics as JSON to this path")
    args = parser.parse_args()

    def write_json(payload: dict) -> None:
        if args.json:
            Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    thresholds = {
        "max_error_rate": args.max_error_rate,
        "max_p95": args.max_p95,
        "max_5xx": args.max_5xx,
    }

    elapsed: list[int] = []
    errors = 0
    server_errors = 0
    first_ts = None
    last_end = None
    with open(args.jtl, newline="") as f:
        for row in csv.DictReader(f):
            ts = int(row["timeStamp"])
            ms = int(row["elapsed"])
            elapsed.append(ms)
            if row["success"] != "true":
                errors += 1
            if row["responseCode"].startswith("5"):
                server_errors += 1
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_end = ts + ms if last_end is None else max(last_end, ts + ms)

    total = len(elapsed)
    if total == 0:
        write_json({
            "jtl": args.jtl, "samples": 0, "errors": None, "error_rate": None,
            "server_5xx": None, "mean_ms": None, "p50_ms": None, "p95_ms": None,
            "p99_ms": None, "max_ms": None, "wall_s": None, "throughput": None,
            "thresholds": thresholds, "failures": ["no samples"], "pass": False,
        })
        print(f"FAIL: {args.jtl} contains no samples")
        return 1

    elapsed.sort()
    error_rate = errors / total * 100
    wall_s = max((last_end - first_ts) / 1000, 0.001)
    mean = sum(elapsed) / total
    p50 = percentile(elapsed, 50)
    p95 = percentile(elapsed, 95)
    p99 = percentile(elapsed, 99)
    throughput = total / wall_s

    failures = []
    if args.max_error_rate is not None and error_rate > args.max_error_rate:
        failures.append(f"error rate {error_rate:.2f}% > {args.max_error_rate}%")
    if args.max_p95 is not None and p95 > args.max_p95:
        failures.append(f"p95 {p95}ms > {args.max_p95}ms")
    if args.max_5xx is not None and server_errors > args.max_5xx:
        failures.append(f"5xx count {server_errors} > {args.max_5xx}")

    write_json({
        "jtl": args.jtl,
        "samples": total,
        "errors": errors,
        "error_rate": round(error_rate, 4),
        "server_5xx": server_errors,
        "mean_ms": round(mean, 2),
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "max_ms": elapsed[-1],
        "wall_s": round(wall_s, 2),
        "throughput": round(throughput, 2),
        "thresholds": thresholds,
        "failures": failures,
        "pass": not failures,
    })

    print(f"samples      : {total}")
    print(f"errors       : {errors} ({error_rate:.2f}%)")
    print(f"5xx          : {server_errors}")
    print(f"latency ms   : mean={mean:.1f} p50={p50} p95={p95} p99={p99} max={elapsed[-1]}")
    print(f"throughput   : {throughput:.1f} req/s over {wall_s:.1f}s")

    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print("PASS: all thresholds met")
    return 0


if __name__ == "__main__":
    sys.exit(main())
