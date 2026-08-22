# UI Automation MVP (Playwright + Pytest)

Minimal UI automation framework with a local demo page as the test target.

## Structure
- `web/login.html` — login page (demo credentials: `demo` / `demo123`)
- `web/demo.html` — main demo page (to-do list, checkbox, counter), gated behind login
- `web/dashboard.html` — mock-data visualization page (bar chart + table + total), gated behind login; fetches `GET /api/stats`
- `web/bugs/` — mutated copies of `demo.html`, each with one injected defect, used for test triage
- `pages/login_page.py`, `pages/demo_page.py`, `pages/dashboard_page.py` — Page Objects
- `tests/` — pytest tests using `pytest-playwright` fixtures
- `scripts/triage.py` — runs `tests/test_demo.py` against every `web/bugs/*.html` and reports which test(s) catch each bug

## Auth: login once, reuse across all tests
The pages are served over local HTTP (via a session-scoped `demo_server` fixture in `tests/conftest.py`, since cookies/localStorage need a real origin — `file://` URLs don't support this reliably).

A session-scoped `storage_state_path` fixture logs in **once** at the start of the test run and saves the resulting storage state (cookies + localStorage) to `.auth/state.json`. That state is injected into every test's browser context via `browser_context_args`, so the `demo_page` fixture used by ordinary tests starts already authenticated — no test logs in itself.

Tests that need to exercise the login flow (or an unauthenticated state) use the `fresh_page` / `login_page` fixtures instead, which spin up a separate browser context without the shared storage state. See `tests/test_login.py`.

## Mock visualization: network mocking with Playwright's `page.route()`
`dashboard.html` fetches `GET /api/stats` and renders the response as a bar chart, a table, and a total. By default the local test server (`DemoRequestHandler` in `tests/conftest.py`) answers that endpoint with a canned JSON payload, so the page works standalone with no mocking at all.

`tests/test_dashboard.py` shows the other side of that: tests call `page.route("**/api/stats", ...)` *before* navigating to intercept the request and substitute controlled data, which is how the empty-state, error-state, and multi-response refresh scenarios are exercised without needing a real backend to produce those conditions on demand.

See [`MOCK_TESTS.md`](MOCK_TESTS.md) (Chinese) for a scenario-by-scenario breakdown of every mock test in `test_dashboard.py`.

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
