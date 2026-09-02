"""Per-step result recorder for Studio runs.

pytest's own report events are per *test*; the Studio's timeline needs to
light up per *step*, so this plugin listens to pytest-bdd's step hooks and
appends one JSON object per step to the file named by STUDIO_STEPS_LOG.

It is loaded with `-p studio.bdd_report_plugin` only by studio/runner.py.
Keeping it out of tests/conftest.py is the point: a daily `pytest` run must
behave exactly as it did before the Studio existed.

Step order in the log is execution order, which is the timeline order the
scenario was rendered from — that is what lets the page map a result back
onto the card the user placed.
"""

import json
import os
import threading
import time

_LOG_PATH = os.environ.get("STUDIO_STEPS_LOG")
_lock = threading.Lock()
_state = {"index": 0, "started": None}


def _record(event: dict) -> None:
    if not _LOG_PATH:
        return
    with _lock, open(_LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def pytest_bdd_before_step(request, feature, scenario, step, step_func):
    _state["started"] = time.monotonic()


def pytest_bdd_after_step(request, feature, scenario, step, step_func, step_func_args):
    _emit(step, "passed", None)


def pytest_bdd_step_error(request, feature, scenario, step, step_func, step_func_args, exception):
    _emit(step, "failed", f"{type(exception).__name__}: {exception}")


def pytest_bdd_step_func_lookup_error(request, feature, scenario, step, exception):
    _emit(step, "failed", f"{type(exception).__name__}: {exception}")


def _emit(step, outcome: str, error: str | None) -> None:
    started = _state["started"]
    _record(
        {
            "index": _state["index"],
            "keyword": step.keyword,
            "name": step.name,
            "outcome": outcome,
            "duration": None if started is None else round(time.monotonic() - started, 3),
            "error": error,
        }
    )
    _state["index"] += 1
    _state["started"] = None
