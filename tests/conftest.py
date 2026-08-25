import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, Playwright

from conftest import PROJECT_ROOT, WEB_DIR
from pages.demo_page import DemoPage
from pages.login_page import LoginPage
from scripts.js_coverage import JsCoverageCollector
from server.app import DEMO_PASSWORD, DEMO_USERNAME, DemoApiHandler

AUTH_STATE_PATH = PROJECT_ROOT / ".auth" / "state.json"
JS_COVERAGE_REPORT_DIR = PROJECT_ROOT / "reports" / "coverage-js"


@pytest.fixture(scope="session")
def demo_server():
    """Serve web/ over local HTTP so cookies/localStorage have a real origin
    (needed for storage_state-based auth reuse; file:// URLs don't support it).
    The handler comes from server/app.py: static files plus the /api/* JSON
    endpoints, running in-process so pytest-cov sees its code execute."""
    handler = partial(DemoApiHandler, directory=str(WEB_DIR))
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


@pytest.fixture(scope="session")
def api_request_context(playwright: Playwright, demo_server: str):
    """Browserless HTTP client for pure API tests (tests/test_api.py)."""
    context = playwright.request.new_context(base_url=demo_server)
    yield context
    context.dispose()


# ---------------------------------------------------------------------------
# Front-end JS coverage ("code staining"): collect V8 precise coverage over
# each page used by a test, merge across the session, and write a colored
# HTML report at session end. See scripts/js_coverage.py.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def js_coverage_collector(demo_server: str):
    collector = JsCoverageCollector(server_url=demo_server, web_dir=WEB_DIR)
    yield collector
    report_path = collector.write_report(JS_COVERAGE_REPORT_DIR)
    if report_path is not None:
        print(f"\nJS coverage report: {report_path}")


@pytest.fixture(autouse=True)
def js_coverage(request: pytest.FixtureRequest, js_coverage_collector: JsCoverageCollector):
    """Instrument every Playwright page a test uses. No-op for API tests."""
    sessions = []
    for fixture_name in ("page", "fresh_page"):
        if fixture_name in request.fixturenames:
            page = request.getfixturevalue(fixture_name)
            sessions.append(js_coverage_collector.start(page))
    yield
    for session in sessions:
        js_coverage_collector.collect(session)
