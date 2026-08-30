from playwright.sync_api import Page, expect

from pages.base_page import BasePage
from pages.i18n import DEFAULT_LOCALE, t


class ProfilePage(BasePage):
    """web/profile.html — opened from demo.html in a new tab (target=_blank),
    or navigated to directly. Construction does not navigate: pass the Page
    that ``DemoPage.open_profile_tab()`` captured, or call ``open()``."""

    PATH = "profile.html"

    def __init__(self, page: Page, base_url: str = "", locale: str = DEFAULT_LOCALE):
        super().__init__(page, base_url, locale)
        # Tier 1 -- role + accessible name (see the policy in base_page.py).
        self.heading = page.get_by_role("heading", name=t("profileTitle", locale))

        # Tier 1, with the same caveat as DashboardPage.error_message: the
        # paragraph is display:none until the fetch fails, so this locator
        # resolves to zero elements in the default and success states. Assert
        # absence with to_have_count(0), not to_be_hidden().
        self.error_message = page.get_by_role("alert")

        # Tier 3 -- unlabelled paragraph and bare text nodes, no accessible
        # name available, so tier 1 does not apply.
        self.loading = page.get_by_test_id("profile-loading")
        self.username_value = page.get_by_test_id("profile-username")
        self.todo_count = page.get_by_test_id("profile-todo-count")

    # --- assertion helpers -------------------------------------------------

    def expect_loaded(self) -> None:
        """Wait until the profile fetch has settled, whichever state it
        settles into (data / error). Web-first: retries until hidden."""
        expect(self.loading).to_be_hidden()

    def expect_profile(self, username: str, todo_count: int) -> None:
        expect(self.username_value).to_have_text(username)
        expect(self.todo_count).to_have_text(str(todo_count))
