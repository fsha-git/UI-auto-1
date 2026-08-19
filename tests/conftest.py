from pathlib import Path

import pytest
from playwright.sync_api import Page

from pages.demo_page import DemoPage

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DEMO_HTML_PATH = PROJECT_ROOT / "web" / "demo.html"


def pytest_addoption(parser):
    parser.addoption(
        "--demo-html",
        action="store",
        default=str(DEFAULT_DEMO_HTML_PATH),
        help="Path to the demo HTML file to run the suite against "
        "(defaults to web/demo.html; use to point at a web/bugs/*.html mutant).",
    )


@pytest.fixture
def demo_page(page: Page, request: pytest.FixtureRequest) -> DemoPage:
    html_path = Path(request.config.getoption("--demo-html")).resolve()
    page.goto(html_path.as_uri())
    return DemoPage(page)
