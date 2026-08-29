from playwright.sync_api import Page, expect

from pages.base_page import BasePage


class DashboardPage(BasePage):
    PATH = "dashboard.html"

    def __init__(self, page: Page, base_url: str = ""):
        super().__init__(page, base_url)
        self.loading = page.get_by_test_id("loading")
        self.error_message = page.get_by_test_id("error-message")
        self.empty_message = page.get_by_test_id("empty-message")
        self.chart_container = page.get_by_test_id("chart-container")
        # Both located by test id rather than by "#chart .bar" / "#stats-table
        # tbody tr": `.bar` is also a *styling* class in dashboard.html, and
        # the row selector hard-coded the <table> structure.
        self.chart_bars = page.get_by_test_id("chart-bar")
        self.table_rows = page.get_by_test_id("stats-row")
        self.total = page.get_by_test_id("total-value")
        self.refresh_btn = page.get_by_test_id("refresh")
        self.logout_btn = page.get_by_test_id("logout")

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
