"""Front-end performance guardrails for dashboard.html and the multi-window
pages (profile.html, popup.html).

The JMeter suite in perf/ measures the *API* only. Nothing there notices if a
chart re-implementation makes rendering 500 bars take seconds in the browser,
so these tests put a coarse budget on the client side.

They are deliberately *order-of-magnitude* guardrails, not SLOs: the budgets
are loose enough to survive a loaded CI box, and exist to catch a regression
that changes the shape of the cost (an O(n^2) render, a forced reflow per bar,
a blocking parse), not to police a few milliseconds. Deselect them with
`pytest -m "not perf"`.
"""

import time

import pytest
from playwright.sync_api import Page, expect

from pages.dashboard_page import DashboardPage
from pages.demo_page import DemoPage
from pages.profile_page import ProfilePage

LARGE_DATASET_SIZE = 500

# Budgets in milliseconds. Generous on purpose — see the module docstring.
RENDER_BUDGET_MS = 3_000
DOM_CONTENT_LOADED_BUDGET_MS = 2_000
POPUP_INTERACTIVE_BUDGET_MS = 3_000

pytestmark = pytest.mark.perf


def _large_payload(size: int) -> dict:
    return {"labels": [f"L{i}" for i in range(size)], "values": [i % 97 for i in range(size)]}


def test_dashboard_renders_large_dataset_within_budget(dashboard: DashboardPage, page: Page):
    payload = _large_payload(LARGE_DATASET_SIZE)
    page.route("**/api/stats", lambda route: route.fulfill(json=payload))

    start = time.perf_counter()
    dashboard.open()
    dashboard.expect_loaded()
    # to_have_count retries, so this resolves as soon as the last bar lands.
    expect(dashboard.chart_bars).to_have_count(LARGE_DATASET_SIZE)
    expect(dashboard.table_rows).to_have_count(LARGE_DATASET_SIZE)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < RENDER_BUDGET_MS, (
        f"rendering {LARGE_DATASET_SIZE} bars + rows took {elapsed_ms:.0f}ms "
        f"(budget {RENDER_BUDGET_MS}ms)"
    )


def test_dashboard_navigation_timing_within_budget(dashboard: DashboardPage, page: Page):
    page.route("**/api/stats", lambda route: route.fulfill(json=_large_payload(50)))

    dashboard.open()
    dashboard.expect_loaded()

    timing = page.evaluate(
        """() => {
            const nav = performance.getEntriesByType('navigation')[0];
            return {
                domContentLoaded: nav.domContentLoadedEventEnd - nav.startTime,
                load: nav.loadEventEnd - nav.startTime,
            };
        }"""
    )
    assert timing["domContentLoaded"] < DOM_CONTENT_LOADED_BUDGET_MS, timing


def test_render_cost_scales_roughly_linearly(dashboard: DashboardPage, page: Page):
    """A 10x bigger dataset must not cost dramatically more than 10x.

    This is the test that actually catches an accidental O(n^2) render; the
    absolute budgets above would not, since both sizes would still pass.
    """
    def render_ms(size: int) -> float:
        page.route("**/api/stats", lambda route: route.fulfill(json=_large_payload(size)))
        start = time.perf_counter()
        dashboard.open()
        dashboard.expect_loaded()
        expect(dashboard.chart_bars).to_have_count(size)
        elapsed = (time.perf_counter() - start) * 1000
        page.unroute("**/api/stats")
        return elapsed

    small = render_ms(50)
    large = render_ms(500)

    # Fixed navigation overhead dominates at these sizes, so the ratio should
    # be well under the 10x size ratio. 10x leaves ample headroom while still
    # failing on quadratic growth (which would land near 100x).
    assert large < small * 10, f"500 bars took {large:.0f}ms vs {small:.0f}ms for 50 (>10x)"


def test_profile_navigation_timing_within_budget(page: Page, demo_server: str):
    profile = ProfilePage(page, demo_server).open()
    profile.expect_loaded()

    timing = page.evaluate(
        """() => {
            const nav = performance.getEntriesByType('navigation')[0];
            return {
                domContentLoaded: nav.domContentLoadedEventEnd - nav.startTime,
                load: nav.loadEventEnd - nav.startTime,
            };
        }"""
    )
    assert timing["domContentLoaded"] < DOM_CONTENT_LOADED_BUDGET_MS, timing


def test_popup_becomes_interactive_within_budget(demo_page: DemoPage):
    """Budget from click to a usable popup: window creation, navigation, and
    the i18n scripts all sit on this path."""
    start = time.perf_counter()
    popup = demo_page.open_quick_note_popup()
    expect(popup.note_input).to_be_visible()
    elapsed_ms = (time.perf_counter() - start) * 1000

    popup.close()
    assert elapsed_ms < POPUP_INTERACTIVE_BUDGET_MS, (
        f"popup took {elapsed_ms:.0f}ms to become interactive "
        f"(budget {POPUP_INTERACTIVE_BUDGET_MS}ms)"
    )
