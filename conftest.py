from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent
WEB_DIR = PROJECT_ROOT / "web"
DEFAULT_DEMO_HTML_PATH = WEB_DIR / "demo.html"


def pytest_addoption(parser):
    parser.addoption(
        "--demo-html",
        action="store",
        default=str(DEFAULT_DEMO_HTML_PATH),
        help="Path to the demo HTML file to run the suite against "
        "(defaults to web/demo.html; use to point at a web/bugs/*.html mutant).",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Embed a screenshot of the page into the pytest-html report for
    failed tests (in addition to the trace/video/screenshot files that
    pytest-playwright's --screenshot/--video/--tracing options save under
    test-results/), so the failure is visible directly in the report."""
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return

    page = item.funcargs.get("page")
    if page is None:
        return

    try:
        import base64

        from pytest_html import extras

        screenshot_b64 = base64.b64encode(page.screenshot()).decode("ascii")
    except Exception:
        return

    report.extras = [*getattr(report, "extras", []), extras.png(screenshot_b64)]
