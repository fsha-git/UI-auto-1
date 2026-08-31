import re

from playwright.sync_api import Page, expect

from pages.base_page import BasePage
from pages.i18n import DEFAULT_LOCALE, t
from pages.popup_page import PopupPage
from pages.profile_page import ProfilePage


class DemoPage(BasePage):
    PATH = "demo.html"

    def __init__(self, page: Page, base_url: str = "", locale: str = DEFAULT_LOCALE):
        super().__init__(page, base_url, locale)
        # Tier 1 -- role + accessible name (see the policy in base_page.py).
        # The input's name comes from its placeholder, which is the weakest
        # source of an accessible name: placeholders get reworded for UX
        # reasons more readily than button labels do.
        self.todo_input = page.get_by_role("textbox", name=t("todoPlaceholder", locale))
        self.add_btn = page.get_by_role("button", name=t("addTodo", locale))
        self.status_checkbox = page.get_by_role("checkbox", name=t("enableFeature", locale))
        self.counter_btn = page.get_by_role("button", name=t("counterIncrement", locale))
        self.logout_btn = page.get_by_role("button", name=t("logout", locale))
        self.profile_link = page.get_by_role("link", name=t("openProfile", locale))
        self.open_popup_btn = page.get_by_role("button", name=t("openPopup", locale))

        # Items are located by ARIA role, not by the `li` tag: wrapping each
        # item in a <div role="listitem"> (or swapping ul/li for a styled
        # list) keeps this working, where "#todo-list li" would break.
        self.todo_list = page.get_by_test_id("todo-list")
        self.todo_items = self.todo_list.get_by_role("listitem")

        # Tier 3 -- these have no accessible name, so tier 1 does not apply:
        # the <ul> is an unlabelled `list`, and the two below are an
        # unlabelled `paragraph` and a bare text node.
        self.status_label = page.get_by_test_id("status-label")
        self.counter = page.get_by_test_id("counter-value")
        self.popup_result = page.get_by_test_id("popup-result")

        # --- trend chart ---------------------------------------------------
        # Tier 1 -- the canvas has role="img" and the chart script sets its
        # aria-label from the same catalog the tests read.
        self.chart_canvas = page.get_by_role("img", name=t("chartTrend", locale))
        self.chart_regenerate_btn = page.get_by_role("button", name=t("chartRegenerate", locale))
        # Tier 3 -- the tooltip/legend are unnamed divs/paragraphs, and the
        # mirror points are hidden <li>s with no accessible name.
        self.chart_tooltip = page.get_by_test_id("chart-tooltip")
        self.chart_legend = page.get_by_test_id("chart-legend")
        self.chart_points = page.get_by_test_id("chart-point")
        # Tier 1, scoped -- each checkbox is named by its wrapping label.
        self.chart_legend_toggles = self.chart_legend.get_by_role("checkbox")

    # --- actions -----------------------------------------------------------

    def add_todo(self, text: str) -> None:
        self.todo_input.fill(text)
        self.add_btn.click()

    def toggle_status(self) -> None:
        self.status_checkbox.click()

    def click_counter(self) -> None:
        self.counter_btn.click()

    def logout(self) -> None:
        self.logout_btn.click()

    # --- multi-window actions ----------------------------------------------
    # The new-page/popup plumbing lives here, not in tests: which Playwright
    # event a click produces (context "page" vs opener "popup") is a property
    # of the UI, and tests should only see the resulting page objects.

    def open_profile_tab(self) -> ProfilePage:
        """Follow the target=_blank profile link; returns the new tab's page
        object. The new tab shares this page's context, so it inherits the
        logged-in storage state."""
        with self.page.context.expect_page() as new_page_info:
            self.profile_link.click()
        return ProfilePage(new_page_info.value, self.base_url, self.locale)

    def open_quick_note_popup(self) -> PopupPage:
        """Click the quick-note button, which window.open()s popup.html."""
        with self.page.expect_popup() as popup_info:
            self.open_popup_btn.click()
        return PopupPage(popup_info.value, self.base_url, self.locale)

    # --- trend chart actions ------------------------------------------------
    # Canvas pixels are opaque to locators, so all the geometry plumbing lives
    # here, against the data mirror contract documented in web/demo.html:
    # every plotted point has a hidden node carrying data-series/-index/-value
    # and its CSS-pixel canvas position in data-px/-py.

    def chart_point(self, series_key: str, index: int):
        """Mirror node for one plotted point. Tier 4 by necessity: hidden
        <li>s have no role or name, and the composite is on the documented
        data-* contract, not on DOM structure."""
        return self.page.locator(
            f'[data-testid="chart-point"][data-series="{series_key}"][data-index="{index}"]'
        )

    def chart_series_points(self, series_key: str):
        return self.page.locator(f'[data-testid="chart-point"][data-series="{series_key}"]')

    def hover_chart_point(self, series_key: str, index: int) -> None:
        """Move the mouse onto a plotted point. The web-first expects retry
        until the mirror node exists with numeric coordinates (and fail
        cleanly if a mutant never writes them); only then are the values
        snapshot-read as action input, and hover(position=...) waits for
        actionability itself."""
        point = self.chart_point(series_key, index)
        expect(point).to_have_attribute("data-px", re.compile(r"^\d+$"))
        expect(point).to_have_attribute("data-py", re.compile(r"^\d+$"))
        x = float(point.get_attribute("data-px"))
        y = float(point.get_attribute("data-py"))
        self.chart_canvas.hover(position={"x": x, "y": y})

    def leave_chart(self) -> None:
        """Park the mouse off the canvas. The target is deliberately inside
        the chart section so this also works on the stripped bug_chart_*
        mutant pages, which carry no other sections."""
        self.chart_regenerate_btn.hover()

    def toggle_series(self, series_key: str) -> None:
        # Tier 1: the series key IS its catalog key, so the checkbox's
        # accessible name (its wrapping label's text) comes straight from t().
        self.chart_legend.get_by_role("checkbox", name=t(series_key, self.locale)).click()

    def regenerate_chart(self) -> None:
        self.chart_regenerate_btn.click()

    # --- assertion helpers -------------------------------------------------
    # These live in the page object (not the test) because they encapsulate
    # *how* the app expresses a piece of state. They stay web-first: every
    # assertion inside retries until it passes or times out.

    def expect_status(self, enabled: bool) -> None:
        """Assert the feature toggle reads as on/off.

        Checks both the control's own state and the rendered label. The label
        is matched by regex on just the ON/OFF token rather than the full
        "Status: ON" copy, so a wording change or i18n pass does not break the
        test — while a label that stops updating at all still fails.
        """
        expect(self.status_checkbox).to_be_checked(checked=enabled)
        expect(self.status_label).to_have_text(re.compile(r"\bON\b" if enabled else r"\bOFF\b"))

    def expect_popup_result(self, text: str) -> None:
        """Assert the note text the quick-note popup posted back. Web-first,
        so it tolerates the postMessage landing after the popup closed."""
        expect(self.popup_result).to_have_text(text)

    def expect_tooltip_for(self, series_key: str, index: int) -> None:
        """Assert the tooltip is showing exactly the hovered point. The
        expected value comes from the point's mirror node — retried into
        existence first, then snapshot-read — so a chart whose tooltip
        renders a different number than it plotted still fails."""
        point = self.chart_point(series_key, index)
        expect(point).to_have_attribute("data-value", re.compile(r"^\d+$"))
        expected = point.get_attribute("data-value")
        expect(self.chart_tooltip).to_be_visible()
        expect(self.chart_tooltip).to_have_attribute("data-series", series_key)
        expect(self.chart_tooltip).to_have_attribute("data-index", str(index))
        expect(self.chart_tooltip).to_have_attribute("data-value", expected)
        expect(self.chart_tooltip).to_contain_text(expected)

    def expect_tooltip_hidden(self) -> None:
        """The count check makes "hidden" mean what it says: to_be_hidden()
        alone also passes when the locator matches nothing (the same caveat
        as role=alert, see pages/dashboard_page.py), so first pin down that
        the tooltip element is still in the DOM."""
        expect(self.chart_tooltip).to_have_count(1)
        expect(self.chart_tooltip).to_be_hidden()

    def expect_visible_series_count(self, count: int) -> None:
        """The chart publishes how many series it actually drew as
        data-series-count on the canvas -- part of the mirror contract."""
        expect(self.chart_canvas).to_have_attribute("data-series-count", str(count))

    def expect_legend_series(self, count: int) -> None:
        expect(self.chart_legend_toggles).to_have_count(count)

    def expect_point_count(self, series_key: str, count: int) -> None:
        expect(self.chart_series_points(series_key)).to_have_count(count)

    def expect_chart_generation(self, generation: int) -> None:
        expect(self.chart_canvas).to_have_attribute("data-generation", str(generation))

    # --- security probes ---------------------------------------------------
    # Intentionally white-box, but owned here so tests don't hand-roll DOM or
    # JS access. The tag name IS the contract for an injection check.

    def injected_script_count(self) -> int:
        return self.todo_list.locator("script").count()

    def xss_flag(self):
        return self.page.evaluate("window.__xss")
