from playwright.sync_api import Page

from pages.base_page import BasePage


class LoginPage(BasePage):
    PATH = "login.html"

    def __init__(self, page: Page, base_url: str = ""):
        super().__init__(page, base_url)
        # Tier 1 throughout (see the policy in base_page.py). The <label for=>
        # elements give both inputs a real accessible name, so get_by_role
        # reaches them directly and get_by_label is an unnecessary demotion.
        # Note <input type="password"> does resolve to role `textbox` --
        # verified against Chromium's computed accessibility tree rather than
        # assumed from the ARIA mapping.
        self.username_input = page.get_by_role("textbox", name="Username")
        self.password_input = page.get_by_role("textbox", name="Password")
        self.login_btn = page.get_by_role("button", name="Log in")
        # This alert is always in the accessibility tree (it is empty until an
        # error occurs, not display:none), so the role locator is stable in
        # every state. Contrast DashboardPage.error_message.
        self.error_message = page.get_by_role("alert")

    def login(self, username: str, password: str) -> None:
        self.username_input.fill(username)
        self.password_input.fill(password)
        self.login_btn.click()
