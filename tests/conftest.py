import json
import threading
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

from conftest import PROJECT_ROOT, WEB_DIR
from pages.demo_page import DemoPage
from pages.login_page import LoginPage

AUTH_STATE_PATH = PROJECT_ROOT / ".auth" / "state.json"

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"

# Canned response for the dashboard's default (unmocked) data source.
STATS_API_RESPONSE = {"labels": ["Mon", "Tue", "Wed", "Thu", "Fri"], "values": [12, 19, 3, 5, 2]}


class DemoRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/stats":
            body = json.dumps(STATS_API_RESPONSE).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


@pytest.fixture(scope="session")
def demo_server():
    """Serve web/ over local HTTP so cookies/localStorage have a real origin
    (needed for storage_state-based auth reuse; file:// URLs don't support it)."""
    handler = partial(DemoRequestHandler, directory=str(WEB_DIR))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    thread.join()


@pytest.fixture
def demo_url(demo_server: str, request: pytest.FixtureRequest) -> str:
    html_path = Path(request.config.getoption("--demo-html")).resolve()
    rel = html_path.relative_to(WEB_DIR)
    return f"{demo_server}/{rel.as_posix()}"


@pytest.fixture(scope="session")
def storage_state_path(browser: Browser, demo_server: str) -> str:
    """Log in once for the whole test session and persist the resulting
    storage state (cookies/localStorage) so individual tests can reuse it
    instead of logging in themselves."""
    AUTH_STATE_PATH.parent.mkdir(exist_ok=True)
    context = browser.new_context()
    page = context.new_page()
    page.goto(f"{demo_server}/login.html")
    LoginPage(page).login(DEMO_USERNAME, DEMO_PASSWORD)
    page.wait_for_url(f"{demo_server}/demo.html")
    context.storage_state(path=str(AUTH_STATE_PATH))
    context.close()
    return str(AUTH_STATE_PATH)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, storage_state_path: str):
    return {**browser_context_args, "storage_state": storage_state_path}


@pytest.fixture
def demo_page(page: Page, demo_url: str) -> DemoPage:
    page.goto(demo_url)
    return DemoPage(page)


@pytest.fixture
def dashboard_url(demo_server: str) -> str:
    return f"{demo_server}/dashboard.html"


@pytest.fixture
def fresh_page(browser: Browser):
    """A page in a brand-new, unauthenticated context — for exercising the
    login flow itself, bypassing the shared logged-in storage state."""
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def login_page(fresh_page: Page, demo_server: str) -> LoginPage:
    fresh_page.goto(f"{demo_server}/login.html")
    return LoginPage(fresh_page)
