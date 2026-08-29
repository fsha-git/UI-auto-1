"""Append one perf-run record to the JSONL history file.

Called by perf/run_perf.sh after each scenario (pass or fail). Combines the
resolved test parameters (JMX defaults overlaid with -J overrides), the
check_jtl.py metrics (check.json) and JMeter's per-label statistics.json into
a single line of reports/jmeter/history.jsonl, which perf/make_dashboard.py
turns into trend charts. Named record_* (not test_*) so pytest never collects it.
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Must mirror the ${__P(name,default)} defaults in perf/*.jmx.
PARAM_DEFAULTS: dict[str, dict[str, int]] = {
    "performance": {"threads": 20, "rampup": 10, "duration": 60},
    "stress": {"threads": 200, "rampup": 120, "duration": 180},
    "concurrency": {"threads": 50, "rampup": 2, "loops": 10, "rendezvous": 50},
    "soak": {"threads": 20, "rampup": 30, "duration": 1800},
    "spike": {
        "threads": 20, "rampup": 10, "duration": 180,
        "spike_threads": 300, "spike_rampup": 5, "spike_duration": 30, "spike_delay": 60,
    },
    "stepload": {"step_threads": 50, "step_rampup": 5, "step_seconds": 60},
}
INFRA_PROPS = {"host", "port"}


def parse_overrides(argv: list[str]) -> dict[str, str]:
    """Extract -Jkey=value tokens (both '-Jk=v' and '-J k=v' forms)."""
    overrides: dict[str, str] = {}
    i = 0
    while i < len(argv):
        token = argv[i]
        pair = None
        if token == "-J" and i + 1 < len(argv):
            pair = argv[i + 1]
            i += 1
        elif token.startswith("-J"):
            pair = token[2:]
        if pair and "=" in pair:
            key, value = pair.split("=", 1)
            if key not in INFRA_PROPS:
                overrides[key] = value
        i += 1
    return overrides


def resolved_params(run_type: str, overrides: dict[str, str]) -> dict:
    """JMX defaults overlaid with -J overrides. Only keys the scenario's JMX
    actually uses (run_perf.sh all 会把同一批 -J 透传给全部场景); the full
    override list is still recorded verbatim in the 'overrides' field."""
    params: dict = dict(PARAM_DEFAULTS.get(run_type, {}))
    for key, value in overrides.items():
        if key not in params:
            continue
        try:
            params[key] = int(value)
        except ValueError:
            params[key] = value
    return params


def load_json_or_none(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", required=True, choices=sorted(PARAM_DEFAULTS))
    parser.add_argument("--out-dir", required=True, help="reports/jmeter/<type> of this run")
    parser.add_argument("--history", required=True, help="JSONL history file to append to")
    parser.add_argument("--jmeter-rc", type=int, required=True)
    parser.add_argument("--check-rc", type=int, required=True)
    parser.add_argument("jmeter_args", nargs="*", help="passthrough jmeter args (after --)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    overrides = parse_overrides(args.jmeter_args)
    now = time.time()
    record = {
        "schema": 1,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
        "epoch": int(now),
        "type": args.type,
        "params": resolved_params(args.type, overrides),
        "overrides": overrides,
        "jmeter_rc": args.jmeter_rc,
        "check_rc": args.check_rc,
        "pass": args.jmeter_rc == 0 and args.check_rc == 0,
        "metrics": load_json_or_none(out_dir / "check.json"),
        "labels": load_json_or_none(out_dir / "dashboard" / "statistics.json"),
    }

    history = Path(args.history)
    history.parent.mkdir(parents=True, exist_ok=True)
    with open(history, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Recorded {args.type} run -> {history}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
