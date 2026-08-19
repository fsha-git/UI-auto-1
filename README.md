# UI Automation MVP (Playwright + Pytest)

Minimal UI automation framework with a local demo page as the test target.

## Structure
- `web/login.html` — login page (demo credentials: `demo` / `demo123`)
- `web/demo.html` — main demo page (to-do list, checkbox, counter), gated behind login
- `web/bugs/` — mutated copies of `demo.html`, each with one injected defect, used for test triage
- `pages/login_page.py`, `pages/demo_page.py` — Page Objects
- `tests/` — pytest tests using `pytest-playwright` fixtures
- `scripts/triage.py` — runs `tests/test_demo.py` against every `web/bugs/*.html` and reports which test(s) catch each bug

## Auth: login once, reuse across all tests
The pages are served over local HTTP (via a session-scoped `demo_server` fixture in `tests/conftest.py`, since cookies/localStorage need a real origin — `file://` URLs don't support this reliably).

A session-scoped `storage_state_path` fixture logs in **once** at the start of the test run and saves the resulting storage state (cookies + localStorage) to `.auth/state.json`. That state is injected into every test's browser context via `browser_context_args`, so the `demo_page` fixture used by ordinary tests starts already authenticated — no test logs in itself.

Tests that need to exercise the login flow (or an unauthenticated state) use the `fresh_page` / `login_page` fixtures instead, which spin up a separate browser context without the shared storage state. See `tests/test_login.py`.

## Setup
```bash
cd /Users/shafelix/mywork2/UI_auto_1
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Run tests
```bash
pytest
```

Run headed (visible browser) to watch the interactions:
```bash
pytest --headed
```
