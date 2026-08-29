from playwright.sync_api import Page

from pages.base_page import BasePage


class LoginPage(BasePage):
    PATH = "login.html"

    def __init__(self, page: Page, base_url: str = ""):
        super().__init__(page, base_url)
        # Semantic locators first: the form already carries <label for=...>
        # and a submit button with an accessible name, so tests survive any
        # restyling or DOM restructuring that preserves the semantics.
        self.username_input = page.get_by_label("Username")
        self.password_input = page.get_by_label("Password")
        self.login_btn = page.get_by_role("button", name="Log in")
        self.error_message = page.get_by_test_id("login-error")

    def login(self, username: str, password: str) -> None:
        self.username_input.fill(username)
        self.password_input.fill(password)
        self.login_btn.click()
