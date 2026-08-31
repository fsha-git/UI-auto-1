#!/usr/bin/env python3
"""Run the matching test file against each buggy demo page in web/bugs/ and
report which test(s) catch each injected defect. (test_login.py is skipped
here since login behavior doesn't vary by --demo-html.)

Which suite runs is picked by the mutant's filename prefix (SUITE_FOR_PREFIX):
plain `bug_*` mutants get tests/test_demo.py, `bug_win_*` mutants get
tests/test_windows.py, and `bug_chart_*` mutants get tests/test_chart.py.
A `bug_win_*` mutant is a demo.html copy whose Windows & Tabs wiring carries
the defect — either directly, or by opening a companion mutant page
(`win_*.html`, no `bug_` prefix so it is not triaged on its own) in place of
the real profile/popup page. A `bug_chart_*` mutant is a demo.html copy
stripped down to the Trend Chart section, with one defect in its script.

Usage:
    python scripts/triage.py [--write TRIAGE.md]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
BUGS_DIR = ROOT / "web" / "bugs"

#: Longest prefix wins; anything unmatched falls back to tests/test_demo.py.
SUITE_FOR_PREFIX = {
    "bug_win_": "tests/test_windows.py",
    "bug_chart_": "tests/test_chart.py",
}
DEFAULT_SUITE = "tests/test_demo.py"


def suite_for(html_path: Path) -> str:
    for prefix, suite in sorted(SUITE_FOR_PREFIX.items(), key=lambda kv: -len(kv[0])):
        if html_path.name.startswith(prefix):
            return suite
    return DEFAULT_SUITE


def run_against(html_path: Path) -> dict:
    report_path = ROOT / f".triage-report-{html_path.stem}.json"
    subprocess.run(
        [
            sys.executable, "-m", "pytest",
            suite_for(html_path),
            f"--demo-html={html_path}",
            f"--report-log={report_path}",
            # Bug pages are *expected* to fail; reruns would only triple the
            # runtime and emit extra "rerun" TestReport events that this
            # script would misread as additional failing tests.
            "--reruns", "0",
            "-q",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    passed, failed = [], []
    if report_path.exists():
        for line in report_path.read_text().splitlines():
            event = json.loads(line)
            if event.get("$report_type") == "TestReport" and event.get("when") == "call":
                name = event["nodeid"].split("::", 1)[1]
                (passed if event["outcome"] == "passed" else failed).append(name)
        report_path.unlink()
    return {"passed": passed, "failed": failed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", default=None, help="Write a Markdown report to this path")
    args = parser.parse_args()

    bug_files = sorted(BUGS_DIR.glob("bug_*.html"))
    if not bug_files:
        print(f"No bug_*.html files found in {BUGS_DIR}")
        sys.exit(1)

    lines = ["# Test Triage Report", "", "Suite run against each injected-bug page.", ""]
    for bug_file in bug_files:
        result = run_against(bug_file)
        lines.append(f"## {bug_file.name}")
        if result["failed"]:
            lines.append("**Caught by:**")
            for name in result["failed"]:
                lines.append(f"- `{name}`")
        else:
            lines.append("**Not caught by any test.**")
        lines.append("")
        status = "CAUGHT" if result["failed"] else "MISSED"
        print(f"[{status}] {bug_file.name}: {', '.join(result['failed']) or '(none)'}")

    report = "\n".join(lines)
    if args.write:
        Path(args.write).write_text(report + "\n")
        print(f"\nWrote {args.write}")


if __name__ == "__main__":
    main()
