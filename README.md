# UI Automation MVP (Playwright + Pytest)

Minimal UI automation framework with a local demo page as the test target.

## Structure
- `web/login.html` — login page (demo credentials: `demo` / `demo123`)
- `web/demo.html` — main demo page (to-do list, checkbox, counter), gated behind login
- `web/dashboard.html` — mock-data visualization page (bar chart + table + total), gated behind login; fetches `GET /api/stats`
- `web/bugs/` — mutated copies of `demo.html`, each with one injected defect, used for test triage
- `server/app.py` — demo backend (static files + `/api/*` JSON endpoints: login, stats, todos CRUD), mounted in-process by the test server fixture
- `pages/base_page.py` — shared page-object plumbing (navigation, session-token access)
- `pages/login_page.py`, `pages/demo_page.py`, `pages/dashboard_page.py` — Page Objects
- `perf/` — JMeter load/stress/step-load/spike/soak/concurrency plans, threshold gate, and cross-run trend dashboard (see [`PERFORMANCE.md`](PERFORMANCE.md))
- `tests/` — pytest tests using `pytest-playwright` fixtures; `tests/test_api.py` are pure API tests via Playwright's `APIRequestContext` (no browser)
- `scripts/triage.py` — runs `tests/test_demo.py` against every `web/bugs/*.html` and reports which test(s) catch each bug
- `scripts/js_coverage.py` — CDP-based V8 precise-coverage collector + colored HTML report generator for the inline JS in `web/*.html`

## Locators: semantic first, never structural
Every element under test carries a `data-testid`, and page objects locate by
`get_by_test_id` / `get_by_role` / `get_by_label` — never by a CSS selector
that encodes DOM structure or styling. The three that used to (`#chart .bar`,
`#stats-table tbody tr`, `#todo-list li`) each broke on a change that left
behaviour intact: `.bar` doubles as a *styling* class, and the other two
hard-coded the `<table>` / `<ul><li>` shape. Todo items are now located by
ARIA role (`listitem`) so wrapping them in a different element still works.

`data-value` on the chart bars is a deliberate, documented **test contract**
(see the comment in `web/dashboard.html`): a chart re-implementation must keep
it, but is otherwise free to change how it renders.

## Assertions: web-first `expect()` only
Tests assert with Playwright's `expect(...)`, which retries until the
assertion passes or times out. Snapshot reads (`text_content()`,
`is_visible()`, `count()`) do not retry and are the classic source of
"passes locally, fails on CI" — e.g. reading an error message the instant a
click returns, before the submit handler has written it.

Page objects therefore expose `Locator` attributes rather than resolved
values. Two knobs keep the layers consistent:

- `expect.set_options(timeout=5000)` in `conftest.py` — the retry window.
- `timeout = 60` in `pytest.ini` — pytest-timeout as a *hang guard only*. It
  used to be `3`, which both caused flakes on slower machines and would have
  silently defeated `expect()` by killing tests inside its retry window.

`--reruns 2` is configured as a safety net, not a fix: a test that only passes
on rerun should be treated as a defect, not as green.

## Auth: login once, reuse across all tests
The pages are served over local HTTP (via a session-scoped `demo_server` fixture in `tests/conftest.py`, since cookies/localStorage need a real origin — `file://` URLs don't support this reliably).

A session-scoped `storage_state_path` fixture logs in **once** at the start of the test run and saves the resulting storage state (cookies + localStorage) to `.auth/state.json`. That state is injected into every test's browser context via `browser_context_args`, so the `demo_page` fixture used by ordinary tests starts already authenticated — no test logs in itself.

Tests that need to exercise the login flow (or an unauthenticated state) use the `fresh_page` / `login_page` fixtures instead, which spin up a separate browser context without the shared storage state. See `tests/test_login.py`.

## Mock visualization: network mocking with Playwright's `page.route()`
`dashboard.html` fetches `GET /api/stats` and renders the response as a bar chart, a table, and a total. By default the local test server (`DemoRequestHandler` in `tests/conftest.py`) answers that endpoint with a canned JSON payload, so the page works standalone with no mocking at all.

`tests/test_dashboard.py` shows the other side of that: tests call `page.route("**/api/stats", ...)` *before* navigating to intercept the request and substitute controlled data, which is how the empty-state, error-state, and multi-response refresh scenarios are exercised without needing a real backend to produce those conditions on demand.

See [`MOCK_TESTS.md`](MOCK_TESTS.md) (Chinese) for a scenario-by-scenario breakdown of every mock test in `test_dashboard.py`.

## Test accounts
The functional suite uses the `demo` account. Load tests use their own
accounts from `perf/accounts.csv` and never share an identity with it — the
server partitions todos per account, so one account can neither read nor
delete another's (`tests/test_api.py` pins this). Sharing a single identity
made per-user isolation structurally untestable.

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

## Coverage ("code staining")
Every `pytest` run instruments both sides of the stack and writes two visual HTML reports:

- **Python** (backend `server/` + Page Objects `pages/`) via pytest-cov → terminal summary plus `reports/coverage-py/index.html`
- **Front-end inline JS** in `web/*.html` via CDP / V8 precise coverage, collected during the UI tests and merged across the session → `reports/coverage-js/index.html` (green = executed, red = never executed)

See [`COVERAGE.md`](COVERAGE.md) (Chinese) for how the API tests and both coverage pipelines work.
