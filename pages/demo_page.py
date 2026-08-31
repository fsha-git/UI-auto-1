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

    # --- security probes ---------------------------------------------------
    # Intentionally white-box, but owned here so tests don't hand-roll DOM or
    # JS access. The tag name IS the contract for an injection check.

    def injected_script_count(self) -> int:
        return self.todo_list.locator("script").count()

    def xss_flag(self):
        return self.page.evaluate("window.__xss")
