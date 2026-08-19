from playwright.sync_api import Page

from pages.demo_page import DemoPage
from pages.login_page import LoginPage


def test_login_with_valid_credentials_redirects_to_demo(login_page: LoginPage):
    login_page.login("demo", "demo123")
    login_page.page.wait_for_url("**/demo.html")
    assert DemoPage(login_page.page).todo_input.is_visible()


def test_login_with_invalid_credentials_shows_error(login_page: LoginPage):
    login_page.login("demo", "wrong-password")
    assert login_page.error_text() == "Invalid username or password"
    assert "login.html" in login_page.page.url


def test_accessing_demo_without_login_redirects_to_login(fresh_page: Page, demo_server: str):
    fresh_page.goto(f"{demo_server}/demo.html")
    fresh_page.wait_for_url("**/login.html")


def test_logout_clears_session_and_redirects_to_login(login_page: LoginPage):
    login_page.login("demo", "demo123")
    login_page.page.wait_for_url("**/demo.html")
    DemoPage(login_page.page).logout()
    login_page.page.wait_for_url("**/login.html")
    token = login_page.page.evaluate("localStorage.getItem('demo_auth_token')")
    assert token is None


def test_demo_page_fixture_starts_already_authenticated(demo_page: DemoPage):
    # The shared session logged in once via storage_state; this fixture never
    # touches login.html, proving no per-test login is happening.
    assert "login.html" not in demo_page.page.url
    assert demo_page.todo_input.is_visible()
