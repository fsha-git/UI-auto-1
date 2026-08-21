from playwright.sync_api import Page


class DashboardPage:
    def __init__(self, page: Page):
        self.page = page
        self.loading = page.locator("#loading")
        self.error_message = page.locator("#error-message")
        self.empty_message = page.locator("#empty-message")
        self.chart_bars = page.locator("#chart .bar")
        self.table_rows = page.locator("#stats-table tbody tr")
        self.total = page.locator("#total-value")
        self.refresh_btn = page.locator("#refresh-btn")

    def wait_for_loaded(self) -> None:
        # #loading is hidden once fetch settles, regardless of which state
        # (data/empty/error) it settles into.
        self.loading.wait_for(state="hidden")

    def bar_values(self) -> list[int]:
        count = self.chart_bars.count()
        return [int(self.chart_bars.nth(i).get_attribute("data-value")) for i in range(count)]

    def row_count(self) -> int:
        return self.table_rows.count()

    def total_value(self) -> int:
        return int(self.total.text_content() or "0")

    def click_refresh(self) -> None:
        self.refresh_btn.click()

    def is_error_visible(self) -> bool:
        return self.error_message.is_visible()

    def is_empty_visible(self) -> bool:
        return self.empty_message.is_visible()

    def error_text(self) -> str:
        return self.error_message.text_content() or ""
