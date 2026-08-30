import re

from playwright.sync_api import Page, expect

from pages.demo_page import DemoPage
from pages.i18n import t
from pages.login_page import LoginPage


def test_login_with_valid_credentials_redirects_to_demo(login_page: LoginPage, fresh_page: Page):
    login_page.login("demo", "demo123")
    expect(fresh_page).to_have_url(re.compile(r"/demo\.html$"))
    expect(DemoPage(fresh_page).todo_input).to_be_visible()


def test_login_with_invalid_credentials_shows_error(login_page: LoginPage, fresh_page: Page):
    login_page.login("demo", "wrong-password")
    # web-first: retries until the submit handler has written the message,
    # instead of snapshotting text_content() the instant the click returns.
    expect(login_page.error_message).to_have_text(t("invalidCredentials"))
    expect(fresh_page).to_have_url(re.compile(r"/login\.html$"))


def test_accessing_demo_without_login_redirects_to_login(fresh_page: Page, demo_server: str):
    fresh_page.goto(f"{demo_server}/demo.html")
    expect(fresh_page).to_have_url(re.compile(r"/login\.html$"))


def test_logout_clears_session_and_redirects_to_login(login_page: LoginPage, fresh_page: Page):
    login_page.login("demo", "demo123")
    expect(fresh_page).to_have_url(re.compile(r"/demo\.html$"))

    demo = DemoPage(fresh_page)
    demo.logout()
    expect(fresh_page).to_have_url(re.compile(r"/login\.html$"))
    # the storage-key name is owned by the page-object layer, not by the test
    assert not demo.has_session()


def test_demo_page_fixture_starts_already_authenticated(demo_page: DemoPage, page: Page):
    # The shared session logged in once via storage_state; this fixture never
    # touches login.html, proving no per-test login is happening.
    expect(page).not_to_have_url(re.compile(r"/login\.html$"))
    expect(demo_page.todo_input).to_be_visible()
