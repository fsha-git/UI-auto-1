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


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def load_baseline(history_path: str | None, run_type: str | None) -> dict | None:
    """Median p95 / throughput of past *passing* runs of the same scenario.

    A single previous run is too noisy to gate on, so this takes the median
    across history. Returns None when there is nothing to compare against —
    the first run of a scenario can never fail the regression gate.
    """
    if not history_path or not run_type:
        return None
    path = Path(history_path)
    if not path.exists():
        return None

    p95s: list[float] = []
    throughputs: list[float] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            run = json.loads(line)
        except ValueError:
            continue
        if run.get("type") != run_type or not run.get("pass"):
            continue
        metrics = run.get("metrics") or {}
        if metrics.get("p95_ms") is not None:
            p95s.append(metrics["p95_ms"])
        if metrics.get("throughput") is not None:
            throughputs.append(metrics["throughput"])

    if not p95s and not throughputs:
        return None
    return {
        "type": run_type,
        "runs": max(len(p95s), len(throughputs)),
        "p95_ms": median(p95s),
        "throughput": median(throughputs),
    }


def regression_failures(
    baseline: dict,
    p95: float,
    throughput: float,
    max_pct: float,
    floor_ms: int,
    min_runs: int,
) -> list[str]:
    """Percentage-change failures vs the historical median, with two guards.

    Both exist because the naive version is unusable in practice:

    * ``min_runs`` — one previous run is a sample, not a baseline. Gating on it
      turns ordinary run-to-run variance into a red build.
    * ``floor_ms`` — on a loopback server p95 sits at 1-2ms, where a single
      millisecond of scheduling jitter is a "+100% regression". Below the floor
      the percentage carries no signal, so only the absolute --max-p95
      threshold applies.
    """
    runs = baseline.get("runs", 0)
    if runs < min_runs:
        return []

    failures = []
    base_p95 = baseline.get("p95_ms")
    if base_p95 and base_p95 >= floor_ms:
        delta = (p95 - base_p95) / base_p95 * 100
        if delta > max_pct:
            failures.append(
                f"p95 regression {delta:+.1f}% vs baseline {base_p95}ms "
                f"(median of {runs} run(s)) > {max_pct}%"
            )
    base_tps = baseline.get("throughput")
    if base_tps:
        delta = (throughput - base_tps) / base_tps * 100
        if -delta > max_pct:
            failures.append(
                f"throughput regression {delta:+.1f}% vs baseline {base_tps:.1f} req/s "
                f"(median of {runs} run(s)) > {max_pct}%"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jtl", help="path to results.jtl (CSV format)")
    parser.add_argument("--max-error-rate", type=float, default=None, help="max error rate in percent")
    parser.add_argument("--max-p95", type=int, default=None, help="max p95 latency in ms")
    parser.add_argument("--max-5xx", type=int, default=None, help="max number of 5xx responses")
    parser.add_argument("--min-throughput", type=float, default=None,
                        help="min sustained throughput in req/s")
    parser.add_argument("--baseline", default=None,
                        help="history.jsonl to compare this run against (regression gate)")
    parser.add_argument("--baseline-type", default=None,
                        help="scenario name to select from --baseline (e.g. performance)")
    parser.add_argument("--max-regression-pct", type=float, default=None,
                        help="fail if p95 rises, or throughput falls, by more than this "
                             "percent versus the median of past passing runs of the same type")
    parser.add_argument("--regression-floor-ms", type=int, default=20,
                        help="skip the p95 regression check while the baseline p95 is below "
                             "this (percent change is meaningless at sub-ms latencies)")
    parser.add_argument("--min-baseline-runs", type=int, default=3,
                        help="minimum passing historical runs before the regression gate applies")
    parser.add_argument("--json", default=None, help="also write metrics as JSON to this path")
    args = parser.parse_args()

    def write_json(payload: dict) -> None:
        if args.json:
            Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    thresholds = {
        "max_error_rate": args.max_error_rate,
        "max_p95": args.max_p95,
        "max_5xx": args.max_5xx,
        "min_throughput": args.min_throughput,
        "max_regression_pct": args.max_regression_pct,
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
    if args.min_throughput is not None and throughput < args.min_throughput:
        failures.append(f"throughput {throughput:.1f} req/s < {args.min_throughput} req/s")

    baseline = load_baseline(args.baseline, args.baseline_type)
    if baseline and args.max_regression_pct is not None:
        failures.extend(regression_failures(
            baseline, p95, throughput,
            max_pct=args.max_regression_pct,
            floor_ms=args.regression_floor_ms,
            min_runs=args.min_baseline_runs,
        ))

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
        "baseline": baseline,
        "thresholds": thresholds,
        "failures": failures,
        "pass": not failures,
    })

    print(f"samples      : {total}")
    print(f"errors       : {errors} ({error_rate:.2f}%)")
    print(f"5xx          : {server_errors}")
    print(f"latency ms   : mean={mean:.1f} p50={p50} p95={p95} p99={p99} max={elapsed[-1]}")
    print(f"throughput   : {throughput:.1f} req/s over {wall_s:.1f}s")
    if baseline:
        gated = baseline["runs"] >= args.min_baseline_runs
        note = "" if gated else f" [gate off: needs >= {args.min_baseline_runs} runs]"
        print(f"baseline     : p95={baseline['p95_ms']}ms throughput={baseline['throughput']:.1f} req/s "
              f"(median of {baseline['runs']} passing run(s)){note}")
        if gated and baseline["p95_ms"] and baseline["p95_ms"] < args.regression_floor_ms:
            print(f"             : p95 gate off (baseline < {args.regression_floor_ms}ms noise floor)")

    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print("PASS: all thresholds met")
    return 0


if __name__ == "__main__":
    sys.exit(main())
