import re

from playwright.sync_api import Page, expect

from pages.base_page import BasePage


class DemoPage(BasePage):
    PATH = "demo.html"

    def __init__(self, page: Page, base_url: str = ""):
        super().__init__(page, base_url)
        # Tier 1 -- role + accessible name (see the policy in base_page.py).
        # The input's name comes from its placeholder, which is the weakest
        # source of an accessible name: placeholders get reworded for UX
        # reasons more readily than button labels do.
        self.todo_input = page.get_by_role("textbox", name="Enter a task")
        self.add_btn = page.get_by_role("button", name="Add")
        self.status_checkbox = page.get_by_role("checkbox", name="Enable feature")
        self.counter_btn = page.get_by_role("button", name="Click me")
        self.logout_btn = page.get_by_role("button", name="Logout")

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
