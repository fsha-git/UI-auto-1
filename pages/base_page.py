from __future__ import annotations

from playwright.sync_api import Page

from pages.i18n import DEFAULT_LOCALE

# ---------------------------------------------------------------------------
# Locator policy, in strict priority order. Every locator in pages/ picks the
# highest tier that is actually available for that element, and says so when
# it has to fall back:
#
#   1. role + accessible name   get_by_role("button", name="Add")
#   2. label / placeholder      get_by_label(...) / get_by_placeholder(...)
#   3. test id                  get_by_test_id(...)   (a purpose-built anchor)
#   4. CSS / XPath              locator(...)          (last resort)
#
# Tiers 1-2 target what a user (or a screen reader) actually perceives, so the
# tests double as a check that the UI is reachable. The cost is that they bind
# to visible copy: renaming a button breaks them. That is a deliberate trade,
# and `data-testid` attributes are kept in the HTML throughout as the tier-3
# anchor to drop back to if the semantics ever regress.
#
# Tier 1 requires a *name*. An element with a role but no accessible name
# (an unlabelled <ul>, a <tr>, a decorative <div>) does not qualify, and
# correctly falls through to its test id.
#
# Because tier 1 binds to visible copy, the names are never spelled out
# here: they come from pages/i18n.py, which reads the same catalogue the
# pages render from. Renaming a button is then one edit, not two.
# ---------------------------------------------------------------------------

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

    def __init__(self, page: Page, base_url: str = "", locale: str = DEFAULT_LOCALE):
        self.page = page
        self.base_url = base_url.rstrip("/")
        #: locale whose copy this page object's role+name locators expect;
        #: the page renders it when the test sets window.__locale to match.
        self.locale = locale

    def open(self, url: str | None = None) -> "BasePage":
        """Navigate to this page. Pass ``url`` to override (used by the
        ``--demo-html`` option, which points the demo suite at a mutant)."""
        self.page.goto(url or f"{self.base_url}/{self.PATH}")
        return self

    def session_token(self) -> str | None:
        return self.page.evaluate(f"localStorage.getItem({AUTH_TOKEN_KEY!r})")

    def has_session(self) -> bool:
        return self.session_token() is not None
