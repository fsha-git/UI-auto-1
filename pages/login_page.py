from playwright.sync_api import Page


class LoginPage:
    def __init__(self, page: Page):
        self.page = page
        self.username_input = page.locator("#username")
        self.password_input = page.locator("#password")
        self.login_btn = page.locator("#login-btn")
        self.error_message = page.locator("#login-error")

    def login(self, username: str, password: str) -> None:
        self.username_input.fill(username)
        self.password_input.fill(password)
        self.login_btn.click()

    def error_text(self) -> str:
        return self.error_message.text_content() or ""
