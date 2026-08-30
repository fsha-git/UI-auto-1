"""Multi-window UI tests: the target=_blank profile tab and the window.open
quick-note popup that demo.html's "Windows & Tabs" section provides.

Kept out of tests/test_demo.py on purpose: scripts/triage.py runs only that
file against the web/bugs/ mutants, and these scenarios are not part of the
recorded mutation contract."""

import re

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from pages.demo_page import DemoPage
from pages.profile_page import ProfilePage
from server.app import DEMO_TOKEN, DEMO_USERNAME, todo_store

AUTH_HEADERS = {"Authorization": f"Bearer {DEMO_TOKEN}"}


@pytest.fixture(autouse=True)
def reset_todo_store():
    """profile.html renders the live todo count from the in-process store;
    reset it around each test so these tests are order-independent."""
    todo_store.reset()
    yield
    todo_store.reset()


# -- profile in a new tab ----------------------------------------------------

def test_profile_link_opens_a_new_tab(demo_page: DemoPage):
    profile = demo_page.open_profile_tab()
    profile.expect_loaded()
    profile.expect_profile(DEMO_USERNAME, 0)


def test_profile_page_shows_live_todo_count(
    demo_page: DemoPage, api_request_context: APIRequestContext
):
    # Seed through the API rather than the UI: the demo page's todo list is
    # client-side only, while the profile counts the server-side store.
    api_request_context.post("/api/todos", data={"text": "first"}, headers=AUTH_HEADERS)
    api_request_context.post("/api/todos", data={"text": "second"}, headers=AUTH_HEADERS)

    profile = demo_page.open_profile_tab()
    profile.expect_loaded()
    profile.expect_profile(DEMO_USERNAME, 2)


def test_profile_page_direct_navigation(page: Page, demo_server: str):
    # Also serves as the JS-coverage anchor for profile.html: this page goes
    # through the pre-instrumented `page` fixture (see tests/conftest.py).
    profile = ProfilePage(page, demo_server).open()
    profile.expect_loaded()
    expect(profile.heading).to_be_visible()
    profile.expect_profile(DEMO_USERNAME, 0)


def test_profile_page_shows_error_when_api_fails(page: Page, demo_server: str):
    page.route("**/api/profile", lambda route: route.fulfill(status=500, json={"error": "boom"}))

    profile = ProfilePage(page, demo_server).open()
    profile.expect_loaded()
    expect(profile.error_message).to_be_visible()
    expect(profile.error_message).to_have_text(re.compile(r"status 500"))


# -- quick-note popup --------------------------------------------------------

def test_popup_sends_note_back_to_opener(demo_page: DemoPage):
    popup = demo_page.open_quick_note_popup()
    popup.send_note("hello from popup")
    # Assert the observable outcome first (expect() retries); only then wait
    # for the popup's self-close, which has no web-first form.
    demo_page.expect_popup_result("hello from popup")
    popup.wait_for_close()


def test_closing_popup_without_sending_leaves_result_empty(demo_page: DemoPage):
    popup = demo_page.open_quick_note_popup()
    popup.close()
    demo_page.expect_popup_result("")


def test_popup_ignores_empty_note(demo_page: DemoPage):
    popup = demo_page.open_quick_note_popup()
    popup.send_note("   ")
    popup.expect_open()
    demo_page.expect_popup_result("")


# -- auth gate on the new pages ----------------------------------------------

def test_profile_page_requires_auth(fresh_page: Page, demo_server: str):
    fresh_page.goto(f"{demo_server}/profile.html")
    expect(fresh_page).to_have_url(re.compile(r"/login\.html$"))


def test_popup_page_requires_auth(fresh_page: Page, demo_server: str):
    fresh_page.goto(f"{demo_server}/popup.html")
    expect(fresh_page).to_have_url(re.compile(r"/login\.html$"))
