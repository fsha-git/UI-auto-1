import re

from playwright.sync_api import Page, expect

from pages.base_page import BasePage


class DemoPage(BasePage):
    PATH = "demo.html"

    def __init__(self, page: Page, base_url: str = ""):
        super().__init__(page, base_url)
        self.todo_input = page.get_by_test_id("todo-input")
        self.add_btn = page.get_by_test_id("add-todo")
        self.todo_list = page.get_by_test_id("todo-list")
        # Items are located by ARIA role, not by the `li` tag: wrapping each
        # item in a <div role="listitem"> (or swapping ul/li for a styled
        # list) keeps this working, where "#todo-list li" would break.
        self.todo_items = self.todo_list.get_by_role("listitem")
        self.status_checkbox = page.get_by_test_id("status-checkbox")
        self.status_label = page.get_by_test_id("status-label")
        self.counter_btn = page.get_by_test_id("counter-increment")
        self.counter = page.get_by_test_id("counter-value")
        self.logout_btn = page.get_by_test_id("logout")

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

    # --- security probes ---------------------------------------------------
    # Intentionally white-box, but owned here so tests don't hand-roll DOM or
    # JS access. The tag name IS the contract for an injection check.

    def injected_script_count(self) -> int:
        return self.todo_list.locator("script").count()

    def xss_flag(self):
        return self.page.evaluate("window.__xss")
