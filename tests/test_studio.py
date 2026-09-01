"""UI tests for the low-code Studio page itself (web/studio.html).

The runner API is mocked with page.route(), which is deliberate twice over:
it keeps these tests fast and hermetic (a real run would spawn a nested
pytest, browser and all), and it exercises the Studio with exactly the
technique the Studio exists to make accessible — the /api/stats mocking
documented in MOCK_TESTS.md.

scripts/triage.py runs this file against the bug_studio_* mutants, the same
way tests/test_windows.py owns bug_win_* and tests/test_chart.py owns
bug_chart_*.
"""

import pytest
from playwright.sync_api import Page, Route, expect

from pages.studio_page import StudioPage

STUB_RUN_ID = "stub-run"
STUB_TRACE_COMMAND = "playwright show-trace reports/studio/runs/stub-run/artifacts/x/trace.zip"
STUB_COMMAND = "python -m pytest --tracing=on --reruns 0 -v tests/test_dashboard.py::test_stub"
STUB_OUTPUT = "collected 1 item\n\ntests/test_dashboard.py::test_stub PASSED [100%]\n\n1 passed in 0.42s"


@pytest.fixture
def stub_runner(page: Page) -> dict:
    """Stand in for the studio backend.

    Returns a mutable dict the test can pre-load with the run result it wants
    to see rendered, and which afterwards holds the payload the page actually
    posted — that is how the "does Run send the *current* timeline?" test
    asserts without reaching into the page.
    """
    state = {
        "posted": None,
        "suites": [
            "tests/test_dashboard.py::test_dashboard_renders_mocked_chart_data",
            "tests/test_dashboard.py::test_dashboard_shows_empty_state_when_no_data",
        ],
        "status": "passed",
        "steps": None,          # None -> one passing result per posted step
        "tests": [],
        "trace_command": STUB_TRACE_COMMAND,
        "command": STUB_COMMAND,
        "output": STUB_OUTPUT,
        "report": "report.html",
        "error": None,
        "trace_opened": False,
        "saved": False,
    }

    def run_payload() -> dict:
        steps = state["steps"]
        if steps is None:
            posted_steps = ((state["posted"] or {}).get("scenario") or {}).get("steps") or []
            steps = [
                {"index": index, "outcome": "passed", "duration": 0.1, "error": None}
                for index, _ in enumerate(posted_steps)
            ]
        return {
            "runId": STUB_RUN_ID,
            "status": state["status"],
            "steps": steps,
            "tests": state["tests"],
            "trace": "artifacts/x/trace.zip",
            "traceCommand": state["trace_command"],
            "command": state["command"],
            "output": state["output"],
            "exitCode": 0,
            "report": state["report"],
            "error": state["error"],
            "duration": 1.23,
        }

    def handle(route: Route) -> None:
        request = route.request
        path = request.url.split("?", 1)[0]
        if path.endswith("/studio/api/suites"):
            route.fulfill(json={"tests": state["suites"]})
        elif path.endswith("/studio/api/run"):
            state["posted"] = request.post_data_json
            route.fulfill(status=202, json={"runId": STUB_RUN_ID, "status": "running"})
        elif path.endswith("/studio/api/scenarios/save"):
            state["saved"] = request.post_data_json
            route.fulfill(json={"path": "tests/features/stub.feature"})
        elif path.endswith("/trace/open"):
            state["trace_opened"] = True
            route.fulfill(json={"trace": "artifacts/x/trace.zip"})
        elif "/studio/api/runs/" in path:
            route.fulfill(json=run_payload())
        else:
            route.fulfill(status=404, json={"error": f"unstubbed {path}"})

    page.route("**/studio/api/**", handle)
    return state


# --- composing --------------------------------------------------------------

def test_a_palette_step_lands_on_the_timeline_with_its_parameters(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    studio_page.open(studio_url)
    studio_page.add_step("g_mock_data", labels="A,B", values="1,2")

    studio_page.expect_timeline(["g_mock_data"])
    studio_page.expect_rendered_step(0, "g_mock_data", labels="A,B", values="1,2")
    studio_page.expect_gherkin_contains(
        'Given the /api/stats endpoint returns labels "A,B" and values "1,2"'
    )


def test_moving_a_step_up_reorders_the_scenario(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    # Order is the meaning of a mock scenario: the endpoint has to be held
    # pending *before* the navigation, or the loading state is never observable.
    studio_page.open(studio_url)
    studio_page.add_step("w_open_dashboard")
    studio_page.add_step("g_mock_pending")
    studio_page.expect_timeline(["w_open_dashboard", "g_mock_pending"])

    studio_page.move_step_up(1)
    studio_page.expect_timeline(["g_mock_pending", "w_open_dashboard"])


def test_moving_a_step_down_reorders_the_scenario(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    studio_page.open(studio_url)
    studio_page.add_step("g_mock_pending")
    studio_page.add_step("w_open_dashboard")

    studio_page.move_step_down(0)
    studio_page.expect_timeline(["w_open_dashboard", "g_mock_pending"])


def test_removing_a_step_drops_it_from_the_timeline_and_the_gherkin(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    studio_page.open(studio_url)
    studio_page.add_step("g_mock_pending")
    studio_page.add_step("w_open_dashboard")

    studio_page.remove_step(0)
    studio_page.expect_timeline(["w_open_dashboard"])
    studio_page.expect_gherkin_excludes("held pending")


def test_clearing_the_timeline_removes_every_step(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    studio_page.open(studio_url)
    studio_page.add_step("g_mock_pending")
    studio_page.add_step("w_open_dashboard")

    studio_page.clear()
    studio_page.expect_timeline([])


def test_the_scenario_name_reaches_the_gherkin_preview(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    studio_page.open(studio_url)
    studio_page.set_scenario_name("Pending request keeps the spinner up")
    studio_page.add_step("w_open_dashboard")

    studio_page.expect_gherkin_contains("Scenario: Pending request keeps the spinner up")


# --- running ----------------------------------------------------------------

def test_run_posts_the_timeline_as_it_stands_now(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    # Edit *after* the first steps are placed: a page that cached the scenario
    # when it was first built would post the stale version.
    studio_page.open(studio_url)
    studio_page.add_step("w_open_dashboard")
    studio_page.add_step("g_mock_pending")
    studio_page.move_step_up(1)
    studio_page.add_step("t_loading_visible")
    studio_page.remove_step(1)

    studio_page.run()
    # Wait on the rendered outcome first: once the lights are painted the
    # response has been applied, so the captured request is settled too.
    studio_page.expect_step_statuses(["passed", "passed"])

    posted = stub_runner["posted"]
    assert posted["mode"] == "scenario"
    assert [item["id"] for item in posted["scenario"]["steps"]] == [
        "g_mock_pending",
        "t_loading_visible",
    ]


def test_run_results_light_each_step_in_timeline_order(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    stub_runner["status"] = "failed"
    stub_runner["steps"] = [
        {"index": 0, "outcome": "passed", "duration": 0.2, "error": None},
        {"index": 1, "outcome": "failed", "duration": 0.4, "error": "AssertionError: nope"},
    ]

    studio_page.open(studio_url)
    studio_page.add_step("g_mock_pending")
    studio_page.add_step("w_open_dashboard")
    studio_page.add_step("t_loading_visible")

    studio_page.run()
    # The third step never ran, so it must read as skipped rather than green.
    studio_page.expect_step_statuses(["passed", "failed", "skipped"])
    studio_page.expect_run_status("failed")


def test_a_failing_run_shows_the_pytest_failure_message(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    stub_runner["status"] = "failed"
    stub_runner["error"] = "AssertionError: Locator expected to have text '7'"

    studio_page.open(studio_url)
    studio_page.add_step("w_open_dashboard")
    studio_page.run()

    expect(studio_page.run_error).to_contain_text("Locator expected to have text")


def test_a_finished_run_offers_its_trace_and_html_report(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    studio_page.open(studio_url)
    studio_page.add_step("w_open_dashboard")
    studio_page.run()

    expect(studio_page.trace_path).to_have_text(STUB_TRACE_COMMAND)
    expect(studio_page.report_link).to_be_visible()


def test_open_trace_asks_the_backend_to_replay_the_last_run(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    studio_page.open(studio_url)
    studio_page.add_step("w_open_dashboard")
    studio_page.run()
    expect(studio_page.trace_path).to_have_text(STUB_TRACE_COMMAND)

    studio_page.open_trace_btn.click()
    expect(studio_page.run_error).to_be_hidden()
    assert stub_runner["trace_opened"] is True


def test_running_an_empty_timeline_never_reaches_the_runner(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    studio_page.open(studio_url)
    studio_page.run()

    studio_page.expect_run_status("invalid")
    assert stub_runner["posted"] is None


def test_saving_a_scenario_reports_the_feature_file_it_wrote(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    studio_page.open(studio_url)
    studio_page.add_step("w_open_dashboard")
    studio_page.save_feature()

    expect(studio_page.save_result).to_have_text("tests/features/stub.feature")


# --- the existing mock tests tab --------------------------------------------

def test_existing_mock_tests_can_be_selected_and_run(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    nodeid = stub_runner["suites"][1]
    stub_runner["steps"] = []

    studio_page.open(studio_url)
    studio_page.open_suite_tab()
    studio_page.select_suite_test(nodeid)
    studio_page.run_selected()

    studio_page.expect_run_status("passed")
    assert stub_runner["posted"] == {"mode": "tests", "nodeids": [nodeid]}


def test_running_existing_mock_tests_lists_one_row_per_test(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    """This mode has no timeline, so without these rows the page would report
    a bare "passed" and nothing else — the user could not tell a real run from
    a no-op."""
    stub_runner["steps"] = []
    stub_runner["status"] = "failed"
    stub_runner["tests"] = [
        {"nodeid": stub_runner["suites"][0], "outcome": "passed", "duration": 0.4, "error": None},
        {"nodeid": stub_runner["suites"][1], "outcome": "failed", "duration": 0.9,
         "error": "AssertionError: nope"},
    ]

    studio_page.open(studio_url)
    studio_page.open_suite_tab()
    studio_page.select_suite_test(stub_runner["suites"][0])
    studio_page.select_suite_test(stub_runner["suites"][1])
    studio_page.run_selected()

    studio_page.expect_test_outcomes(["passed", "failed"])
    expect(studio_page.test_results.nth(1)).to_contain_text("test_dashboard_shows_empty_state")
    # to_be_visible, not just present: the result panel used to live inside the
    # compose panel, which this tab hides — so every row rendered into a
    # display:none container and the user saw nothing at all.
    expect(studio_page.test_results.first).to_be_visible()
    expect(studio_page.run_output).to_be_visible()
    expect(studio_page.run_command).to_be_visible()
    studio_page.expect_run_status("failed")


def test_a_run_shows_the_command_it_executed(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    studio_page.open(studio_url)
    studio_page.add_step("w_open_dashboard")
    studio_page.run()

    expect(studio_page.run_command).to_have_text(STUB_COMMAND)


def test_a_run_shows_the_pytest_output(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    studio_page.open(studio_url)
    studio_page.add_step("w_open_dashboard")
    studio_page.run()

    expect(studio_page.run_output).to_contain_text("1 passed in 0.42s")
    expect(studio_page.run_output).to_contain_text("collected 1 item")
    expect(studio_page.run_output).to_be_visible()


def test_each_run_replaces_the_previous_run_s_output(
    studio_page: StudioPage, studio_url: str, stub_runner: dict
):
    # Stale output from the last run reading as this run's evidence is the
    # exact confusion these panes exist to remove.
    studio_page.open(studio_url)
    studio_page.add_step("w_open_dashboard")
    studio_page.run()
    expect(studio_page.run_output).to_contain_text("1 passed in 0.42s")

    stub_runner["output"] = "collected 2 items\n\n2 passed in 1.10s"
    studio_page.run()
    expect(studio_page.run_output).to_have_text("collected 2 items\n\n2 passed in 1.10s")


# --- auth -------------------------------------------------------------------

def test_studio_requires_auth(fresh_page: Page, demo_server: str, studio_url: str):
    fresh_page.goto(studio_url)
    fresh_page.wait_for_url(f"{demo_server}/login.html")
