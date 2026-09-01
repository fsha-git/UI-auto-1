"""HTTP surface of the Studio: web/ plus the /studio/api/* runner endpoints.

StudioHandler subclasses server/app.py's DemoApiHandler rather than editing
it, so the application under test keeps exactly the endpoint surface the
JMeter plans baseline (see the note in studio/__init__.py). One process still
serves everything, which matters: studio.html, dashboard.html and /api/stats
have to share an origin for the scenarios to be about the real app.
"""

from __future__ import annotations

import errno
import json
import subprocess
from functools import lru_cache, partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from server.app import DemoApiHandler
from studio import runner
from studio.runner import ScenarioError, registry

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
API_PREFIX = "/studio/api/"


@lru_cache(maxsize=1)
def mock_test_nodeids() -> tuple[str, ...]:
    """Cached because it shells out to `pytest --collect-only`; the list only
    changes when someone edits tests/test_dashboard.py, which means restarting
    the studio anyway."""
    return tuple(runner.collect_mock_tests())


class StudioHandler(DemoApiHandler):
    protocol_version = "HTTP/1.1"

    # --- helpers -----------------------------------------------------------

    def _run_json(self, run_id: str) -> None:
        run = registry.get(run_id)
        if run is None:
            self._send_json(404, {"error": f"unknown run {run_id}"})
        else:
            self._send_json(200, run.to_json())

    # --- GET ---------------------------------------------------------------

    def do_GET(self):
        if not self.path.startswith(API_PREFIX):
            super().do_GET()
            return

        route = self.path[len(API_PREFIX):]
        if route == "suites":
            self._send_json(200, {"tests": list(mock_test_nodeids())})
        elif route.startswith("runs/") and route.count("/") == 1:
            self._run_json(route.removeprefix("runs/"))
        elif route.startswith("runs/") and "/artifacts/" in route:
            run_id, _, relative = route.removeprefix("runs/").partition("/artifacts/")
            self._send_artifact(run_id, unquote(relative))
        else:
            self._send_json(404, {"error": "not found"})

    def _send_artifact(self, run_id: str, relative: str) -> None:
        """Serve one file out of a run directory (trace.zip, report.html).

        runner.resolve_artifact enforces that the path stays inside the run
        directory.
        """
        run = registry.get(run_id)
        if run is None:
            self._send_json(404, {"error": f"unknown run {run_id}"})
            return
        target = runner.resolve_artifact(run.directory, relative)
        if target is None:
            self._send_json(404, {"error": "no such artifact"})
            return
        data = target.read_bytes()
        # The HTML report is meant to be read in the tab the link opens; the
        # trace archive is meant to be saved and fed to `playwright show-trace`.
        is_report = target.suffix == ".html"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8" if is_report
                         else "application/octet-stream")
        if not is_report:
            self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # --- POST --------------------------------------------------------------

    def do_POST(self):
        if not self.path.startswith(API_PREFIX):
            super().do_POST()
            return

        route = self.path[len(API_PREFIX):]
        # _read_json returns None for a body that is not valid JSON; every
        # handler below rejects a non-dict payload with a 400 of its own.
        payload = self._read_json()

        if route == "run":
            self._start_run(payload)
        elif route == "scenarios/save":
            self._save_scenario(payload)
        elif route.startswith("runs/") and route.endswith("/trace/open"):
            self._open_trace(route.removeprefix("runs/").removesuffix("/trace/open"))
        else:
            self._send_json(404, {"error": "not found"})

    def _start_run(self, payload: object) -> None:
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "request body must be a JSON object"})
            return
        mode = payload.get("mode")
        try:
            if mode == "scenario":
                scenario = runner.validate_scenario(payload.get("scenario"))
                run = registry.start("scenario", scenario=scenario)
            elif mode == "tests":
                nodeids = self._validated_nodeids(payload.get("nodeids"))
                run = registry.start("tests", nodeids=nodeids)
            else:
                self._send_json(400, {"error": "mode must be 'scenario' or 'tests'"})
                return
        except ScenarioError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except RuntimeError as exc:
            self._send_json(409, {"error": str(exc)})
            return
        self._send_json(202, run.to_json())

    def _validated_nodeids(self, raw: object) -> list[str]:
        """Only node ids pytest itself collected are runnable.

        This is the whole allow-list: it keeps the run endpoint from becoming
        a way to make this process execute an arbitrary path.
        """
        if not isinstance(raw, list) or not raw:
            raise ScenarioError("select at least one test")
        known = set(mock_test_nodeids())
        # isinstance first, for the same reason as the step-id check in
        # studio/runner.py: `{} in known` raises TypeError on a set, and a
        # crash is not a rejection. repr() keeps a hostile value printable
        # and bounded in the message that goes back to the client.
        unknown = [item for item in raw if not isinstance(item, str) or item not in known]
        if unknown:
            listed = ", ".join(repr(item)[:80] for item in unknown[:5])
            raise ScenarioError(f"unknown test(s): {listed}")
        return list(raw)

    def _save_scenario(self, payload: object) -> None:
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "request body must be a JSON object"})
            return
        try:
            scenario = runner.validate_scenario(payload.get("scenario"))
        except ScenarioError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        path = runner.save_feature(scenario)
        self._send_json(200, {"path": runner.display_path(path)})

    def _open_trace(self, run_id: str) -> None:
        run = registry.get(run_id)
        if run is None or not run.trace:
            self._send_json(404, {"error": "this run has no trace"})
            return
        trace_path = (run.directory / run.trace).resolve()
        # `playwright show-trace` opens a local viewer window; fire and forget.
        subprocess.Popen(
            ["playwright", "show-trace", str(trace_path)],
            cwd=runner.ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._send_json(200, {"trace": run.trace})


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True


class PortInUseError(RuntimeError):
    """The studio port is already bound — usually by a studio left running."""

    def __init__(self, host: str, port: int):
        super().__init__(
            f"port {port} on {host} is already in use.\n"
            f"  Something is already listening there — most likely an earlier\n"
            f"  `python -m studio` you forgot to stop. Find it with:\n"
            f"      lsof -nP -iTCP:{port} -sTCP:LISTEN\n"
            f"  Then stop that process, or start this one on another port:\n"
            f"      python -m studio --port {port + 1}"
        )


def serve(host: str = "127.0.0.1", port: int = 8100) -> None:
    """Bind and serve until Ctrl-C. Raises PortInUseError if the port is taken."""
    handler = partial(StudioHandler, directory=str(WEB_DIR))
    try:
        httpd = StudioServer((host, port), handler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        # Restarting the studio is a routine thing to do, and forgetting to
        # stop the old one is the routine way to get here — say so instead of
        # printing a socket traceback.
        raise PortInUseError(host, port) from None

    print(f"Mock Scenario Studio on http://{host}:{httpd.server_port}/studio.html", flush=True)
    print(f"Collected {len(mock_test_nodeids())} existing mock test(s)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
