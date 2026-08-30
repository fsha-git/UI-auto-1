from playwright.sync_api import Page, expect

from pages.base_page import BasePage


class DashboardPage(BasePage):
    PATH = "dashboard.html"

    def __init__(self, page: Page, base_url: str = ""):
        super().__init__(page, base_url)
        # Tier 1 -- role + accessible name (see the policy in base_page.py).
        self.refresh_btn = page.get_by_role("button", name="Refresh")
        self.logout_btn = page.get_by_role("button", name="Logout")

        # Tier 1, with a caveat worth knowing. This paragraph is display:none
        # until a request fails, so it is absent from the accessibility tree
        # in the default and success states and this locator resolves to
        # *zero* elements there (the test id would resolve to one).
        #
        # Every assertion below is "it appeared / it says X", which expect()
        # retries into, so that is fine. But it means the locator cannot tell
        # "hidden" apart from "deleted": to assert that no error is shown,
        # write expect(dashboard.error_message).to_have_count(0) rather than
        # relying on to_be_hidden(), which would also pass if the element were
        # removed from the page entirely.
        self.error_message = page.get_by_role("alert")

        # Tier 3 -- no accessible name available, so tier 1 does not apply:
        # unlabelled paragraphs, a bare text node, an unnamed container, an
        # unnamed `row`, and SVG <rect> elements with no role at all.
        # Still preferable to "#chart .bar" / "#stats-table tbody tr": `.bar`
        # doubles as a *styling* class, and the row selector hard-coded the
        # <table> structure.
        self.loading = page.get_by_test_id("loading")
        self.empty_message = page.get_by_test_id("empty-message")
        self.chart_container = page.get_by_test_id("chart-container")
        self.chart_bars = page.get_by_test_id("chart-bar")
        self.table_rows = page.get_by_test_id("stats-row")
        self.total = page.get_by_test_id("total-value")

    # --- actions -----------------------------------------------------------

    def click_refresh(self) -> None:
        self.refresh_btn.click()

    # --- assertion helpers -------------------------------------------------

    def expect_loaded(self) -> None:
        """Wait until the fetch has settled, whichever state it settles into
        (data / empty / error). Web-first: retries until #loading is hidden."""
        expect(self.loading).to_be_hidden()

    def expect_bar_values(self, values: list[int]) -> None:
        """Assert the chart renders exactly ``values``, in order.

        Owns the `data-value` test contract (see the comment in
        dashboard.html) so that a chart re-implementation only has to keep
        that attribute, not match a selector shape.
        """
        expect(self.chart_bars).to_have_count(len(values))
        for index, value in enumerate(values):
            expect(self.chart_bars.nth(index)).to_have_attribute("data-value", str(value))

    def expect_total(self, total: int) -> None:
        expect(self.total).to_have_text(str(total))

    def expect_row_count(self, count: int) -> None:
        expect(self.table_rows).to_have_count(count)
