"""Browserless tests for the Studio backend (studio/runner.py, studio/server.py).

Same shape as tests/test_api.py: no Playwright page involved, so these run in
milliseconds. They cover the parts of the Studio that are pure data — the step
catalogue and the Gherkin renderer — plus the validation and path handling
that make up its security boundary. Nothing here ever starts a run: spawning a
nested pytest inside pytest is exactly what tests/test_studio.py avoids by
mocking the runner API.
"""

import json
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

import pytest

from pages import studio_steps
from pages.studio_steps import (
    KEYWORDS,
    LANES,
    load_steps,
    render_step,
    step_ids,
    step_param_names,
)
from studio import runner, server
from studio.runner import ScenarioError
from studio.server import StudioHandler
from tests.test_dashboard_bdd import IMPLEMENTED


def _scenario(*steps):
    return {"name": "A scenario", "steps": list(steps)}


# --- the catalogue is the single source of truth ----------------------------

def test_every_catalogued_step_has_an_implementation():
    """The parity check that makes the palette honest.

    A step in web/studio.js with no step definition would only fail once a
    user happened to compose it, as an "undefined step" deep inside a run;
    an implementation with no catalogue entry is dead code no palette can
    reach. Both are caught here instead.
    """
    assert IMPLEMENTED == set(step_ids())


def test_catalogue_entries_are_well_formed():
    for step_id, spec in load_steps().items():
        assert spec["keyword"] in KEYWORDS, step_id
        assert spec["lane"] in LANES, step_id
        declared = [param["name"] for param in spec["params"]]
        assert declared == step_param_names(step_id), (
            f"{step_id}: params and template placeholders disagree"
        )
        for param in spec["params"]:
            assert param["type"] in ("text", "int"), step_id
            assert param["default"] != "", f"{step_id}: {param['name']} needs a default"


def test_render_step_substitutes_parameters_and_falls_back_to_defaults():
    assert render_step("g_mock_status", {"status": "404"}).endswith("404")
    assert render_step("g_mock_status") == render_step("g_mock_status", {"status": "500"})


def test_render_step_rejects_a_non_integer_where_the_catalogue_says_integer():
    with pytest.raises(ValueError, match="must be an integer"):
        render_step("g_mock_status", {"status": "not a number"})


def test_unknown_step_id_raises_and_lists_the_known_ones():
    with pytest.raises(KeyError, match="unknown studio step"):
        render_step("no_such_step")


def test_a_malformed_step_catalogue_fails_loudly(tmp_path, monkeypatch):
    """Same contract as pages/i18n.py's catalogue reader: a steps.js that no
    longer assigns window.STUDIO_STEPS must blow up here, not silently hand
    back an empty palette."""
    broken = tmp_path / "steps.js"
    broken.write_text("// no assignment here\n")
    monkeypatch.setattr(studio_steps, "STEPS_PATH", broken)
    studio_steps.load_steps.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="no window.STUDIO_STEPS assignment"):
            studio_steps.load_steps()
    finally:
        studio_steps.load_steps.cache_clear()


# --- Gherkin rendering ------------------------------------------------------

def test_render_feature_keeps_the_timeline_order():
    """Order is the scenario's meaning: "held pending" has to be written
    before the navigation, and the release after the loading assertion."""
    scenario = runner.validate_scenario(
        _scenario(
            {"id": "g_mock_pending"},
            {"id": "w_open_dashboard"},
            {"id": "t_loading_visible"},
            {"id": "w_release_pending", "params": {"labels": "A", "values": "7"}},
        )
    )
    body = runner.render_feature(scenario)
    lines = [line.strip() for line in body.splitlines() if line.strip().startswith(("Given", "When", "Then"))]
    assert lines == [
        "Given the /api/stats endpoint is held pending",
        "When I open the dashboard",
        "Then the loading indicator is visible",
        'When I release the pending /api/stats request with labels "A" and values "7"',
    ]


def test_render_feature_puts_the_scenario_name_on_one_line():
    scenario = runner.validate_scenario(
        {"name": "  broken\nover   lines  ", "steps": [{"id": "w_open_dashboard"}]}
    )
    assert "  Scenario: broken over lines\n" in runner.render_feature(scenario)


def test_a_blank_name_gets_the_default():
    scenario = runner.validate_scenario({"name": "   ", "steps": [{"id": "w_open_dashboard"}]})
    assert scenario["name"] == runner.DEFAULT_SCENARIO_NAME


def test_slugify_produces_a_filesystem_safe_stem():
    assert runner.slugify("Loading state: 500 / error!") == "loading_state_500_error"
    assert runner.slugify("!!!") == "studio_scenario"


# --- validation is the security boundary ------------------------------------

def test_an_unknown_step_id_is_rejected():
    with pytest.raises(ScenarioError, match="unknown step id"):
        runner.validate_scenario(_scenario({"id": "rm -rf /"}))


def test_an_unknown_parameter_is_rejected():
    with pytest.raises(ScenarioError, match="unknown parameter"):
        runner.validate_scenario(_scenario({"id": "w_open_dashboard", "params": {"shell": "sh"}}))


def test_a_bad_parameter_type_is_rejected():
    with pytest.raises(ScenarioError, match="must be an integer"):
        runner.validate_scenario(_scenario({"id": "g_mock_status", "params": {"status": "abc"}}))


def test_an_empty_scenario_is_rejected():
    with pytest.raises(ScenarioError, match="at least one step"):
        runner.validate_scenario({"name": "empty", "steps": []})


def test_a_non_object_scenario_is_rejected():
    with pytest.raises(ScenarioError, match="must be a JSON object"):
        runner.validate_scenario(json.loads("[1, 2, 3]"))


# --- the artifact download guard --------------------------------------------

def test_resolve_artifact_finds_a_file_inside_the_run_directory(tmp_path):
    (tmp_path / "report.html").write_text("<html></html>")
    assert runner.resolve_artifact(tmp_path, "report.html") == (tmp_path / "report.html").resolve()


def test_resolve_artifact_refuses_to_walk_out_of_the_run_directory(tmp_path):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert runner.resolve_artifact(run_dir, "../secret.txt") is None


def test_resolve_artifact_returns_none_for_a_missing_file(tmp_path):
    assert runner.resolve_artifact(tmp_path, "artifacts/trace.zip") is None


# --- the HTTP surface -------------------------------------------------------
# The Studio serves web/ *and* /studio/api/*, so both halves are checked here:
# the app under test must still be reachable, and the runner endpoints must
# reject anything the catalogue or the collected node ids do not vouch for.

@pytest.fixture(scope="module")
def studio_api():
    """The Studio's own HTTP server on an ephemeral loopback port."""
    handler = partial(StudioHandler, directory=str(server.WEB_DIR))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    thread.join()


def _request(base_url: str, path: str, payload=None) -> tuple[int, dict | None]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        base_url + path, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request) as response:
            body = response.read()
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return exc.code, (json.loads(body) if body else None)


def test_the_studio_still_serves_the_app_under_test(studio_api: str):
    status, _ = _request(studio_api, "/api/health")
    assert status == 200


def test_the_studio_serves_its_own_page(studio_api: str):
    with urllib.request.urlopen(studio_api + "/studio.html") as response:
        assert response.status == 200
        assert b'data-testid="timeline"' in response.read()


def test_the_suite_list_comes_from_pytest_itself(studio_api: str):
    status, body = _request(studio_api, "/studio/api/suites")
    assert status == 200
    # Not a hardcoded copy of MOCK_TESTS.md: whatever tests/test_dashboard.py
    # currently defines is what the Studio offers. The emptiness check is
    # load-bearing -- a collection that silently returns nothing would make
    # every other assertion here vacuously true, which is exactly how the
    # first version of this shipped broken.
    assert body["tests"], "no mock tests collected"
    assert body["tests"] == list(server.mock_test_nodeids())
    assert all(nodeid.startswith("tests/test_dashboard.py::") for nodeid in body["tests"])
    assert any("test_dashboard_shows_loading_state" in nodeid for nodeid in body["tests"])


def test_an_unknown_step_id_is_refused_before_anything_is_spawned(studio_api: str):
    status, body = _request(
        studio_api,
        "/studio/api/run",
        {"mode": "scenario", "scenario": {"name": "x", "steps": [{"id": "; rm -rf /"}]}},
    )
    assert status == 400
    assert "unknown step id" in body["error"]


def test_a_node_id_outside_the_collected_list_is_refused(studio_api: str):
    status, body = _request(
        studio_api, "/studio/api/run", {"mode": "tests", "nodeids": ["tests/test_demo.py"]}
    )
    assert status == 400
    assert "unknown test" in body["error"]


def test_an_unknown_mode_is_refused(studio_api: str):
    status, body = _request(studio_api, "/studio/api/run", {"mode": "shell"})
    assert status == 400
    assert "mode must be" in body["error"]


def test_an_unknown_run_id_is_a_404(studio_api: str):
    status, body = _request(studio_api, "/studio/api/runs/no-such-run")
    assert status == 404
    assert "unknown run" in body["error"]


def test_saving_a_scenario_writes_a_feature_file(studio_api: str, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "FEATURES_DIR", tmp_path)
    status, body = _request(
        studio_api,
        "/studio/api/scenarios/save",
        {"scenario": {"name": "Saved from the studio", "steps": [{"id": "w_open_dashboard"}]}},
    )
    assert status == 200
    written = tmp_path / "saved_from_the_studio.feature"
    assert written.exists()
    assert "When I open the dashboard" in written.read_text()
    assert body["path"].endswith("saved_from_the_studio.feature")
