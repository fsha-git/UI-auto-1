"""BDD step definitions for the dashboard's Mock scenarios.

This is the execution engine behind the low-code Studio page
(web/studio.html): the Studio composes an ordered timeline of steps, renders
it as a real Gherkin .feature file, and runs *this* module against it. So a
scenario a non-coder assembled in the browser is executed by the same pytest,
the same fixtures (demo_server / storage_state / page) and the same page
objects as every hand-written test in tests/ — there is no second execution
path to keep honest.

Two rules keep it that way:

- **Every Gherkin sentence comes from web/studio/steps.js**, via
  pages/studio_steps.py. ``bdd_step()`` below builds the pytest-bdd decorator
  out of the catalogue entry, so the sentence and its keyword have exactly one
  definition site and the palette can never drift from what runs.
- **Every step goes through DashboardPage**, never through the DOM directly,
  and every assertion is a web-first ``expect()`` — the same constraints
  AGENTS.md §3/§5 put on hand-written tests. ``page.route()`` is used for the
  mocks, which is test-level control of the environment, not UI knowledge.

Which features run:

- normally, every ``.feature`` in tests/features/ — scenarios promoted out of
  the Studio with "save as feature" become part of the daily regression run;
- when ``STUDIO_FEATURE`` names a file, only that one. The Studio sets it for
  a one-shot run so its transient scenario (under reports/studio/) executes
  without ever being written into tests/features/. It has to be an environment
  variable rather than a pytest option because ``scenarios()`` binds at import
  time, before a pytest option would be readable.
"""

import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, Route, expect
from pytest_bdd import given, parsers, scenarios, then, when

from pages.dashboard_page import DashboardPage
from pages.studio_steps import step
from tests.conftest import wait_for_intercepted_route

FEATURES_DIR = Path(__file__).parent / "features"
STATS_URL_PATTERN = "**/api/stats"

#: Step ids this module actually implements. tests/test_studio_backend.py
#: asserts it equals the catalogue, so a step that exists in the palette but
#: has no implementation (or the reverse) fails loudly instead of surfacing as
#: an "undefined step" only when someone happens to compose it.
IMPLEMENTED: set[str] = set()

_DECORATOR_FOR_KEYWORD = {"Given": given, "When": when, "Then": then}


def bdd_step(step_id: str):
    """Register a step definition against the catalogue's own sentence."""
    spec = step(step_id)
    IMPLEMENTED.add(step_id)
    return _DECORATOR_FOR_KEYWORD[spec["keyword"]](parsers.parse(spec["template"]))


# --- parameter parsing ------------------------------------------------------
# Studio parameters are flat strings (they come from text inputs and travel
# through a Gherkin sentence), so the list shapes are parsed here, once.

def _labels(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _values(raw: str) -> list[int]:
    return [int(part) for part in _labels(raw)]


def _datasets(raw: str) -> list[dict]:
    """``A=1 | A,B=1,2`` -> the successive /api/stats payloads."""
    payloads = []
    for chunk in raw.split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        labels, _, values = chunk.partition("=")
        payloads.append({"labels": _labels(labels), "values": _values(values)})
    if not payloads:
        raise ValueError(f"no datasets found in {raw!r}")
    return payloads


@pytest.fixture
def mock_state() -> dict:
    """Per-scenario bookkeeping shared by the mock steps: the route captured
    by "held pending", and the cursor into a dataset sequence."""
    return {}


# --- Given: the state of the /api/stats endpoint ----------------------------

@bdd_step("g_no_mock")
def _no_mock():
    """Install nothing: the scenario exercises the server's real endpoint."""


@bdd_step("g_mock_data")
def _mock_data(page: Page, labels: str, values: str):
    payload = {"labels": _labels(labels), "values": _values(values)}
    page.route(STATS_URL_PATTERN, lambda route: route.fulfill(json=payload))


@bdd_step("g_mock_empty")
def _mock_empty(page: Page):
    # A dedicated step rather than "labels=\"\" values=\"\"": parse's {name}
    # placeholder never matches an empty string, and an empty text box is a
    # bad affordance in a palette anyway.
    page.route(STATS_URL_PATTERN, lambda route: route.fulfill(json={"labels": [], "values": []}))


@bdd_step("g_mock_status")
def _mock_status(page: Page, status: int):
    page.route(
        STATS_URL_PATTERN,
        lambda route: route.fulfill(status=status, body="Internal Server Error"),
    )


@bdd_step("g_mock_aborted")
def _mock_aborted(page: Page):
    # A connection-level failure (DNS/refused/offline), distinct from an HTTP
    # error response like 500.
    page.route(STATS_URL_PATTERN, lambda route: route.abort())


@bdd_step("g_mock_malformed")
def _mock_malformed(page: Page, body: str):
    page.route(
        STATS_URL_PATTERN,
        lambda route: route.fulfill(status=200, content_type="application/json", body=body),
    )


@bdd_step("g_mock_pending")
def _mock_pending(page: Page, mock_state: dict):
    # Capture the route without completing it, so the fetch stays pending
    # until a later step releases it. This is what makes the loading state
    # observable with no sleep and no race — see MOCK_TESTS.md.
    page.route(STATS_URL_PATTERN, lambda route: mock_state.setdefault("pending", route))


@bdd_step("g_mock_sequence")
def _mock_sequence(page: Page, mock_state: dict, datasets: str):
    payloads = _datasets(datasets)
    mock_state["sequence_index"] = 0

    def handle_route(route: Route):
        index = min(mock_state["sequence_index"], len(payloads) - 1)
        mock_state["sequence_index"] += 1
        route.fulfill(json=payloads[index])

    page.route(STATS_URL_PATTERN, handle_route)


# --- When: what the user (or the clock) does --------------------------------

@bdd_step("w_open_dashboard")
def _open_dashboard(dashboard: DashboardPage):
    dashboard.open()


@bdd_step("w_click_refresh")
def _click_refresh(dashboard: DashboardPage):
    dashboard.click_refresh()


@bdd_step("w_release_pending")
def _release_pending(page: Page, mock_state: dict, labels: str, values: str):
    route = wait_for_intercepted_route(page, mock_state, key="pending")
    route.fulfill(json={"labels": _labels(labels), "values": _values(values)})


@bdd_step("w_wait_loaded")
def _wait_loaded(dashboard: DashboardPage):
    dashboard.expect_loaded()


# --- Then: web-first assertions, all via the page object --------------------

@bdd_step("t_bars")
def _expect_bars(dashboard: DashboardPage, values: str):
    dashboard.expect_bar_values(_values(values))


@bdd_step("t_no_bars")
def _expect_no_bars(dashboard: DashboardPage):
    dashboard.expect_bar_values([])


@bdd_step("t_total")
def _expect_total(dashboard: DashboardPage, total: int):
    dashboard.expect_total(total)


@bdd_step("t_rows")
def _expect_rows(dashboard: DashboardPage, count: int):
    dashboard.expect_row_count(count)


@bdd_step("t_empty_visible")
def _expect_empty_visible(dashboard: DashboardPage):
    expect(dashboard.empty_message).to_be_visible()


@bdd_step("t_empty_hidden")
def _expect_empty_hidden(dashboard: DashboardPage):
    expect(dashboard.empty_message).to_be_hidden()


@bdd_step("t_error_visible")
def _expect_error_visible(dashboard: DashboardPage):
    expect(dashboard.error_message).to_be_visible()


@bdd_step("t_error_contains")
def _expect_error_contains(dashboard: DashboardPage, text: str):
    expect(dashboard.error_message).to_contain_text(text)


@bdd_step("t_loading_visible")
def _expect_loading_visible(dashboard: DashboardPage):
    expect(dashboard.loading).to_be_visible()


# The catalogue/implementation parity check lives in
# tests/test_studio_backend.py, not here: asserting it at import time would
# break this module's *collection*, and with it the very test meant to explain
# the mismatch.

# Bound last: scenarios() injects one test function per scenario into this
# module, and the step definitions above have to be registered by then.
_STUDIO_FEATURE = os.environ.get("STUDIO_FEATURE")
scenarios(_STUDIO_FEATURE if _STUDIO_FEATURE else str(FEATURES_DIR))
