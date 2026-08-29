from __future__ import annotations

from playwright.sync_api import Page

# The demo app's session key. This is an *implementation detail of the app*:
# it lives here, inside the page-object layer, so tests never have to know it
# (and so renaming it is a one-line change).
AUTH_TOKEN_KEY = "demo_auth_token"


class BasePage:
    """Common plumbing for every page object.

    Page objects expose Playwright ``Locator`` objects as attributes rather
    than returning already-resolved strings/ints. That is deliberate: a
    Locator is lazy and re-queries on every access, which is what lets tests
    assert with web-first ``expect(...)`` and get automatic retrying. Methods
    that snapshot a value (``.text_content()``, ``.count()``) do NOT retry and
    are a flakiness source, so they are avoided outside of narrow cases.
    """

    #: path of this page relative to the server root, e.g. "demo.html"
    PATH: str = ""

    def __init__(self, page: Page, base_url: str = ""):
        self.page = page
        self.base_url = base_url.rstrip("/")

    def open(self, url: str | None = None) -> "BasePage":
        """Navigate to this page. Pass ``url`` to override (used by the
        ``--demo-html`` option, which points the demo suite at a mutant)."""
        self.page.goto(url or f"{self.base_url}/{self.PATH}")
        return self

    def session_token(self) -> str | None:
        return self.page.evaluate(f"localStorage.getItem({AUTH_TOKEN_KEY!r})")

    def has_session(self) -> bool:
        return self.session_token() is not None
