import threading
import time
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, Playwright, Route

from conftest import PROJECT_ROOT, WEB_DIR
from pages.dashboard_page import DashboardPage
from pages.demo_page import DemoPage
from pages.login_page import LoginPage
from pages.studio_page import StudioPage
from scripts.js_coverage import JsCoverageCollector
from server.app import DEMO_PASSWORD, DEMO_USERNAME, DemoApiHandler

AUTH_STATE_PATH = PROJECT_ROOT / ".auth" / "state.json"
JS_COVERAGE_REPORT_DIR = PROJECT_ROOT / "reports" / "coverage-js"
#: Machine-readable twin of the HTML report, read by the diff-coverage gate
#: (`docker compose run --rm tests coverage`). See COVERAGE.md 六.
JS_COVERAGE_XML_PATH = JS_COVERAGE_REPORT_DIR / "coverage.xml"
BUGS_DIR = WEB_DIR / "bugs"


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
    LoginPage(page, demo_server).open().login(DEMO_USERNAME, DEMO_PASSWORD)
    page.wait_for_url(f"{demo_server}/demo.html")
    context.storage_state(path=str(AUTH_STATE_PATH))
    context.close()
    return str(AUTH_STATE_PATH)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, storage_state_path: str):
    return {**browser_context_args, "storage_state": storage_state_path}


@pytest.fixture
def demo_page(page: Page, demo_server: str, demo_url: str) -> DemoPage:
    # demo_url is passed explicitly because --demo-html can point the suite at
    # a web/bugs/*.html mutant instead of demo.html.
    return DemoPage(page, demo_server).open(demo_url)


@pytest.fixture
def dashboard(page: Page, demo_server: str) -> DashboardPage:
    """An un-navigated dashboard page object. Tests call ``.open()`` themselves
    so they can install page.route() interception *before* navigating."""
    return DashboardPage(page, demo_server)


def wait_for_intercepted_route(page: Page, pending: dict, key: str = "route",
                               timeout_ms: int = 5_000) -> Route:
    """Block until page.route() has actually intercepted the request.

    page.goto() resolves on the `load` event, which carries no guarantee that
    the route handler has already run — reading pending[key] straight
    after open() is a race. Every Playwright call pumps the event loop, so
    this polls the real condition instead of assuming it.

    Lives here rather than in a test file because two suites need it:
    tests/test_dashboard.py's pending-request test and the "held pending" /
    "release the pending request" pair of BDD steps in
    tests/test_dashboard_bdd.py. It is test-level control of the environment,
    not UI knowledge, so it stays out of pages/.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    while key not in pending:
        if time.monotonic() > deadline:
            raise AssertionError("the /api/stats request was never intercepted")
        page.wait_for_timeout(50)
    return pending[key]


#: Filename prefix of the Studio mutants (see scripts/triage.py). --demo-html
#: normally points the demo suite at a mutant of demo.html; the Studio suite
#: only takes it over when it is pointed at one of *its* mutants.
STUDIO_MUTANT_PREFIX = "bug_studio_"


@pytest.fixture
def studio_url(demo_server: str, request: pytest.FixtureRequest) -> str:
    """URL of the low-code Studio page.

    Honours --demo-html only when it names a bug_studio_* mutant, so
    scripts/triage.py can feed a Studio mutant to tests/test_studio.py while a
    plain `pytest` run (whose --demo-html defaults to web/demo.html) still
    gets the real page.
    """
    html_path = Path(request.config.getoption("--demo-html")).resolve()
    if not html_path.name.startswith(STUDIO_MUTANT_PREFIX):
        html_path = WEB_DIR / StudioPage.PATH
    return f"{demo_server}/{html_path.relative_to(WEB_DIR).as_posix()}"


@pytest.fixture
def studio_page(page: Page, demo_server: str, studio_url: str) -> StudioPage:
    """An un-navigated Studio page object. Tests call ``.open(studio_url)``
    themselves so they can install page.route() interception of the runner
    API *before* navigating — the same shape as the ``dashboard`` fixture."""
    return StudioPage(page, demo_server)


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
    return LoginPage(fresh_page, demo_server).open()


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
def js_coverage_collector(demo_server: str, request: pytest.FixtureRequest):
    collector = JsCoverageCollector(server_url=demo_server, web_dir=WEB_DIR)
    yield collector

    # scripts/triage.py runs this suite once per mutant page, and each of those
    # sessions only ever touches that one mutant's scripts. Letting them write
    # would leave the *last mutant's* report on disk in place of the real
    # suite's — which is what the diff-coverage gate then reads. Same trap the
    # --no-cov in triage.py closes on the Python side; see COVERAGE.md 六.
    demo_html = Path(request.config.getoption("--demo-html")).resolve()
    if demo_html.parent == BUGS_DIR.resolve():
        return

    report_path = collector.write_report(JS_COVERAGE_REPORT_DIR)
    if report_path is not None:
        print(f"\nJS coverage report: {report_path}")
    xml_path = collector.write_cobertura(JS_COVERAGE_XML_PATH)
    if xml_path is not None:
        print(f"JS coverage XML:    {xml_path}")


@pytest.fixture(autouse=True)
def js_coverage(request: pytest.FixtureRequest, js_coverage_collector: JsCoverageCollector):
    """Instrument every Playwright page a test uses. No-op for API tests.

    Pages born *during* the test (window.open popups, target=_blank tabs) are
    instrumented too, via a context "page" listener. Caveat: their CDP session
    attaches only after the new page has started loading, so top-level inline
    script statements that already ran can show as red-but-executed in the
    report; tests/test_windows.py compensates with direct navigations through
    the pre-instrumented ``page`` fixture."""
    sessions = []
    contexts = []

    def instrument_late_page(late_page: Page) -> None:
        sessions.append(js_coverage_collector.start(late_page))

    for fixture_name in ("page", "fresh_page"):
        if fixture_name in request.fixturenames:
            page = request.getfixturevalue(fixture_name)
            sessions.append(js_coverage_collector.start(page))
            if page.context not in contexts:
                contexts.append(page.context)
                page.context.on("page", instrument_late_page)
    yield
    for context in contexts:
        context.remove_listener("page", instrument_late_page)
    # One combined pass: a popup shares its opener's V8 isolate, and taking
    # coverage drains that isolate for all its pages at once — see
    # JsCoverageCollector.collect_all for why sessions can't be collected
    # one at a time.
    js_coverage_collector.collect_all(sessions)
