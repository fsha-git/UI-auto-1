from playwright.sync_api import Page, expect

from pages.base_page import BasePage
from pages.i18n import DEFAULT_LOCALE, t

#: Matches EXPECT_TIMEOUT_MS in the root conftest.py: waiting for the popup
#: to close itself deserves the same patience as any web-first assertion.
CLOSE_TIMEOUT_MS = 5_000


class PopupPage(BasePage):
    """web/popup.html — the quick-note window that demo.html window.open()s.

    Never navigated to via ``open()`` in normal use: construct it around the
    Page that ``DemoPage.open_quick_note_popup()`` captured.
    """

    PATH = "popup.html"

    def __init__(self, page: Page, base_url: str = "", locale: str = DEFAULT_LOCALE):
        super().__init__(page, base_url, locale)
        # Tier 1 -- role + accessible name (see the policy in base_page.py).
        # The input's name comes from its placeholder, same trade-off as
        # DemoPage.todo_input.
        self.note_input = page.get_by_role("textbox", name=t("popupNotePlaceholder", locale))
        self.send_btn = page.get_by_role("button", name=t("popupSend", locale))

    # --- actions -----------------------------------------------------------

    def send_note(self, text: str) -> None:
        self.note_input.fill(text)
        self.send_btn.click()

    def close(self) -> None:
        self.page.close()

    # --- assertion helpers -------------------------------------------------

    def wait_for_close(self, timeout_ms: int = CLOSE_TIMEOUT_MS) -> None:
        """Wait for the popup to close *itself* (it does after a successful
        send). Page lifetime has no web-first expect() form, so this is the
        one place that waits on an event instead; callers should assert the
        observable outcome (the opener's result text) first."""
        if not self.page.is_closed():
            self.page.wait_for_event("close", timeout=timeout_ms)

    def expect_open(self) -> None:
        """Assert the popup is still up and interactive (e.g. after a send
        that should have been rejected)."""
        expect(self.send_btn).to_be_visible()
