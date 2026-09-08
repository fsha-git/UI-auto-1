# AGENTS.md — working rules for this repository

Conventions here were set by a review along six axes: locator fragility, flaky
protection, load-test account isolation, decoupling from UI internals, load
coverage, and copy management. They are not stylistic preferences — each one
replaced something that was actually broken. Follow them, and run the checks in
[Verification](#verification) before claiming anything works.

`README.md` explains the framework to a human. This file is the rulebook: what
you must not break, and how to prove you didn't.

---

## 1. The invariant that matters most

**`web/bugs/bug_*.html` are 30 frozen mutants, each carrying one injected
defect. `scripts/triage.py` runs the matching test file against every one —
`tests/test_demo.py` for the classic demo mutants, `tests/test_windows.py` for
the `bug_win_*` multi-window mutants, `tests/test_chart.py` for the
`bug_chart_*` trend-chart mutants, `tests/test_studio.py` for the
`bug_studio_*` low-code studio mutants (see `SUITE_FOR_PREFIX` in the script)
— and records which tests catch which bug in `TRIAGE.md`.**

```bash
.venv/bin/python scripts/triage.py --write /tmp/TRIAGE_new.md
diff TRIAGE.md /tmp/TRIAGE_new.md      # MUST be empty
```

A non-empty diff means your change silently weakened the suite's ability to
detect real defects. That is the most expensive kind of regression in a test
framework, and nothing else you did matters until it is fixed. The one
legitimate non-empty diff is **purely additive**: a change that introduces new
mutants regenerates and commits `TRIAGE.md` in the same change, and every
pre-existing section must remain byte-identical.

Three rules follow:

- **Changing shared static markup in `web/demo.html` means changing all 11
  mutants too.** They are byte-identical to it in the regions tests locate
  (`Add`, `Click me`, `Enable feature`, `placeholder="Enter a task"`, plus the
  `data-testid` and `data-i18n` attributes). Patch all 12 with one script and
  assert the expected markup is present in each, rather than editing by hand.
- **Never touch the JS the mutants deliberately break** — status-label
  rendering, the counter, and todo-item creation in `web/demo.html`. Each
  mutant's defect lives in exactly that code. This is why the copy catalogue
  (§4) covers only static markup: rewriting that JS would put the injected
  defects at risk for no gain.
- **New feature tests ship with mutants.** A new UI feature area with its own
  test file also gets at least one frozen mutant per defect class those tests
  claim to catch, so the triage report *proves* the detection instead of
  asserting it. To add a group: pick a filename prefix (`bug_win_*` is the
  multi-window group), map it in `SUITE_FOR_PREFIX` in `scripts/triage.py`,
  and regenerate `TRIAGE.md`. Where the defect lives in a page other than the
  one `--demo-html` swaps (e.g. the profile tab or the popup), the `bug_*`
  mutant is a demo copy that opens a **companion mutant page** — named without
  the `bug_` prefix (`win_profile_count_static.html`) so triage never runs it
  directly. Every mutant must be CAUGHT; a MISSED entry is a missing test, not
  a report to commit.

The classic mutants are older copies that predate the auth gate, the logout
button, and the Windows & Tabs section; the `bug_win_*` mutants carry only the
Windows & Tabs section, the `bug_chart_*` mutants only the Trend Chart
section, and the `bug_studio_*` mutants are copies of `web/studio.html`
(a different page entirely). All are expected: a mutant only needs to support
the test file triage runs against it — which is also why multi-window tests
live in `tests/test_windows.py`, trend-chart tests in `tests/test_chart.py`,
and low-code studio tests in `tests/test_studio.py`, never in
`tests/test_demo.py`.

A mutant of a page that is not `demo.html` needs a fixture that knows when to
take `--demo-html` over. `studio_url` in `tests/conftest.py` is the pattern:
it honours the option only when it names a `bug_studio_*` file, so triage can
target the studio suite while a plain `pytest` run (whose `--demo-html`
defaults to `web/demo.html`) still gets the real page.

---

## 2. Locators: a strict priority ladder

Defined once, in `pages/base_page.py`. Every locator takes the **highest tier
actually available for that element**, and says in a comment when it falls back.
See [`LOCATORS.md`](LOCATORS.md) for the fuller write-up (rationale, the two
documented traps, and how this ties into the copy catalogue in §4) — the rules
below are the enforceable summary.

| Tier | Locator |
|---|---|
| 1 | role + accessible name — `get_by_role("button", name=...)` |
| 2 | label / placeholder — `get_by_label` / `get_by_placeholder` |
| 3 | test id — `get_by_test_id` (a purpose-built anchor) |
| 4 | CSS / XPath — `locator(...)` |

**Tier 1 requires a *name*.** An element with a role but no accessible name — an
unlabelled `<ul>` (`list`), a `<tr>` (`row`), a decorative `<div>` — does not
qualify and correctly falls through to its test id. The tier-3 locators in this
repo are measured absences of an accessible name, not oversights.

**Do not guess at ARIA roles — measure them.** Chromium's computed accessibility
tree is the authority, and it has already contradicted the spec-from-memory
answer once here: `<input type="password">` *does* resolve to role `textbox`.
Probe with `locator.aria_snapshot()` or `get_by_role(...).count()` before
deciding a tier is unavailable.

Never write a selector that encodes DOM structure or styling. The three that
used to exist (`#chart .bar`, `#stats-table tbody tr`, `#todo-list li`) each
broke on a change that left behaviour intact — `.bar` doubles as a styling
class, the other two hard-coded the `<table>` / `<ul><li>` shape.

`data-testid` attributes stay in the HTML even where a tier-1 locator is used:
they are the anchor to drop back to if semantics ever regress.

### Two documented traps

- **`data-value` on the chart bars is a test contract**, not an implementation
  detail. It is commented as such in `web/dashboard.html`. A chart
  re-implementation must keep it.
- **`DashboardPage.error_message` and `ProfilePage.error_message` are tier 1
  with a caveat.** Those paragraphs are `display:none` until a request fails, so
  they are absent from the accessibility tree and `get_by_role("alert")`
  resolves to **zero** elements in the default and success states. Assertions of
  the form "it appeared / it says X" are fine (`expect()` retries into them). To
  assert that *no* error is shown, use `to_have_count(0)` — `to_be_hidden()`
  would also pass if the element were deleted outright.

---

## 3. Assertions: web-first `expect()` only

Never assert on a snapshot read. `text_content()`, `all_text_contents()`,
`is_visible()`, `count()` and `get_attribute()` do not retry, and are the classic
source of "passes locally, fails on CI".

```python
expect(demo_page.counter).to_have_text("3")          # yes
assert demo_page.counter.text_content() == "3"       # no
```

Page objects therefore expose `Locator` **attributes**, not resolved values.
Where an assertion needs domain knowledge, put an `expect_*` helper on the page
object (`DashboardPage.expect_bar_values`, `DemoPage.expect_status`) so the
knowledge stays in one place and stays retrying.

### The timeout budget — do not break this ordering

```
pytest.ini  timeout = 60     hang guard, nothing more
conftest.py expect  = 5s     assertion retry window
```

**The retry window must stay well below the hang guard.** This was `timeout = 3`
originally: the largest flake source in the repo, *and* it would have silently
defeated `expect()` by killing tests inside their own retry window. If you raise
the expect timeout, raise the hang guard too.

`--reruns 2` is a safety net, not a fix. A test that only passes on rerun is a
defect; investigate it rather than banking the green.

`scripts/triage.py` passes `--reruns 0` deliberately — mutant pages are
*expected* to fail, so reruns would triple its runtime and emit extra `rerun`
report events that it would misread as additional failing tests.

---

## 4. Copy: one catalogue, read by both sides

Tier-1 locators bind to visible text, so **no user-visible string may be
hardcoded in `pages/` or `tests/`**. `web/i18n/catalog.js` is the single source
of truth, read by the browser (`web/i18n/apply.js`) and by the tests
(`pages/i18n.py`).

```python
self.add_btn = page.get_by_role("button", name=t("addTodo", locale))
```

- The catalogue is `.js`, not `.json`, so pages load it with a plain `<script>`
  tag — no `fetch`, so no window in which a locator runs before the text is
  applied. Its object literal is **strict JSON**; `pages/i18n.py` parses it with
  `json.loads` and will fail loudly otherwise. Keep it that way: no comments, no
  trailing commas, no single quotes inside the braces.
- `t()` raises on an unknown key or locale. Do not add a silent fallback — it
  resurfaces much later as a locator that mysteriously matches nothing.
- Adding a locale means adding every key. `tests/test_i18n.py` enforces key
  parity **and** that no two locales share a translation, so a locale added but
  never actually translated cannot pass while proving nothing.

Scope is limited to copy a locator or assertion depends on — see §1 for why the
mutant-varied JS is excluded. `expect_status()` still hardcodes `ON`/`OFF` for
exactly that reason; changing it requires solving the mutant problem first.

**The same pattern, applied twice.** `web/studio/steps.js` is a second
catalogue built the same way — a `.js` file loaded with a plain `<script>`
tag, strict JSON inside the braces, parsed test-side by `pages/studio_steps.py`
— and for the same reason: a step's Gherkin sentence is read by the studio
page, by `pages/studio_page.py`, by the pytest-bdd step definitions in
`tests/test_dashboard_bdd.py`, and by `studio/runner.py`. One definition site,
four readers. Gherkin keywords (`Given`/`When`/`Then`) stay literal English in
both files: they are syntax, not UI copy, and putting them in the i18n
catalogue would also collide with the "no two locales share a translation"
check.

---

## 5. Page objects own the UI, tests do not

**No test may reach through a page object into the DOM, `localStorage`, or
`window`.** `grep -rn '_page\.page\.' tests/` should stay empty.

- Navigation lives in `BasePage.open()`.
- The session key (`demo_auth_token`) lives in `pages/base_page.py`; tests call
  `has_session()`.
- White-box probes are page-object methods (`DemoPage.injected_script_count`,
  `xss_flag`), not `page.evaluate` in a test.

Prefer semantic assertions over copy assertions where both are possible.
`expect_status()` checks the checkbox's own state **and** matches the label with
a regex on just the `ON`/`OFF` token, rather than the full `"Status: ON"` string
— so rewording does not break it, while a label that stops updating still fails.
That second half is load-bearing: `bug_checkbox_label_static` is caught only by
the label assertion.

Using the `page` fixture directly for network interception (`page.route(...)`) is
fine — that is test-level control of the environment, not UI knowledge.

**Multi-window plumbing is page-object plumbing.** Which Playwright event a
click produces (`context.expect_page()` for a `target=_blank` tab,
`page.expect_popup()` for `window.open`) is a property of the UI, so it lives in
`DemoPage.open_profile_tab()` / `open_quick_note_popup()`, which return the new
window's page object. Tests never call `expect_popup` / `wait_for_event`
themselves — the one sanctioned event wait is `PopupPage.wait_for_close()`,
because page lifetime has no web-first `expect()` form; assert the observable
outcome (the opener's result text) *before* waiting on it.

---

## 6. Load and performance testing

### Accounts

**Never point a load test at the `demo` account.** `perf/accounts.csv` holds 50
dedicated accounts, registered via `python -m server --accounts`. The server
partitions `todo_store` per owner: one account can neither read nor delete
another's (`tests/test_api.py` pins this).

Per-scenario account strategy is deliberate and differs:

| Scenario | Accounts | Why |
|---|---|---|
| performance / stress / stepload / spike / soak | CSV Data Set over 50 accounts | realistic multi-user traffic |
| concurrency | one fixed account | it wants **maximum contention on a single partition**, and its tearDown assertion ("this account's store is empty") only means something if every thread wrote to the same one |

Todo ids come from one global counter, not per user — that is what keeps
`concurrency.jmx` able to detect a duplicate id handed to two threads.

### Scenarios

Seven plans in `perf/`, each answering a different question: `performance`
(baseline load), `stepload` (capacity knee — each level held long enough to
read, unlike a linear ramp), `spike` (recovery after a burst), `soak` (drift and
leaks; excluded from `all` because it defaults to 30 min), `stress` (linear
ramp), `concurrency` (rendezvous correctness), `profile` (read-only baseline for
`GET /api/profile`). `stepload` uses four stock thread groups with staggered
delays — **do not introduce a jmeter-plugins dependency.**

**Tooling endpoints are out of scope.** This rule is about the *application
under test*. `studio/`'s `/studio/api/*` endpoints run pytest on request; they
live on a `StudioHandler(DemoApiHandler)` subclass precisely so `server/app.py`
— and therefore the baseline — is untouched. Never add them to a `.jmx`.

**A new endpoint gets a new scenario, not new samplers in an old one.** The
regression gate compares each scenario against the median of its own past runs;
mixing a new request into an existing plan changes its latency profile and
quietly redefines that baseline. That is why `profile` is a separate JMX.
Registering a scenario touches four places: the `.jmx`, `run_perf.sh` (usage
comment, target `case`, `thresholds_for`), `record_run.py` (`PARAM_DEFAULTS`,
mirroring the JMX's `${__P(...)}` defaults), and `make_dashboard.py`
(`TYPE_ORDER` / `TYPE_TITLES`).

### The regression gate has two guards — leave them in

`check_jtl.py` compares against the median of past *passing* runs of the same
scenario. Both guards exist because the naive version misfired on its first real
run, reporting a "+100% p95 regression" for 1 ms → 2 ms:

- `--regression-floor-ms` (20): below this, percentage change carries no signal.
- `--min-baseline-runs` (3): one previous run is a sample, not a baseline.

### Known-good gaps, do not "fix" them

- `server/__main__.py` shows 0% coverage. It only runs under load tests, never
  under pytest. Expected.
- `server/app.py` has one uncovered line, `fake_function`. It is an intentional
  demo of an uncovered branch (commit `51fe60f`). Leave it.
- Both of those are known-good *gaps*, not known-good *diffs*. The increment gate
  (COVERAGE.md 六) only looks at lines a PR changes, so they cost nothing while
  they sit still — but a PR that edits either one is a PR whose changed lines are
  0% stained, and turning `coverage-gate` green then takes the `coverage-waiver`
  label plus a written reason. That is the intended behaviour: touching
  deliberately untested code is exactly the decision a human should sign off on.
- A `pages/` method whose **first line is covered and the rest is red** is a
  broken ruler, not a missing test. Playwright's sync API switches greenlets on
  every `click()` / `fill()` / `goto()`, and coverage.py's default C tracer stops
  recording the rest of the function when it switches back. It only bites where
  that tracer is in use — Python 3.14 (the usual local venv) defaults to
  `sys.monitoring` and is immune, while the container and CI run 3.12 and are
  not, so the suite passes 150/150 and still reports `pages/` at 82–94% there.
  `concurrency = greenlet,thread` in `.coveragerc` is what holds this shut;
  `thread` is not optional (dropping it takes `server/app.py` from 99% to 35%,
  because `demo_server` runs it on a `ThreadingHTTPServer` thread). Do not write
  tests against these phantom gaps — check that config line first, and verify a
  coverage change on **both** interpreters. See COVERAGE.md 二 and 六.
- Absolute perf numbers do not extrapolate: the load generator shares a machine
  with the service over loopback, and `ThreadingHTTPServer` is itself the
  bottleneck. This suite's value is **relative** — trends, concurrency
  correctness, regression gating. `PERFORMANCE.md` states this; keep it stated.

---

## 7. Docs ship with the change

The Markdown docs are read by both humans and tooling agents; a doc that
describes last month's code is worse than no doc, because it gets trusted.
**Any change to an area below updates its paired doc in the same change** — not
in a follow-up:

| If you touched… | Update |
|---|---|
| pages, page objects, test files, perf scenarios, or how anything is run | `README.md` (项目结构 table, 运行测试 commands, the intro's feature list) |
| any locator in `pages/` (added, removed, or moved between tiers) | `LOCATORS.md` — **recount the tier table from the code** (`grep get_by_role / get_by_test_id / locator(` over `pages/`), don't adjust it incrementally; extend the documented-traps list if the new locator carries a caveat |
| `server/app.py` endpoints, either coverage pipeline (`scripts/js_coverage.py`, the `js_coverage` fixture, `pytest.ini`'s `--cov*` flags, `.coveragerc`), or the diff-coverage gate (`entrypoint.sh`'s `coverage` task, its `diff-cover` flags, the `coverage-comment` / `coverage-gate` jobs and the label-waiver rule) | `COVERAGE.md` — endpoint table, pipeline description, 第六节's gate 口径 and waiver flow, and refresh the 快照 section's date/numbers when they materially change |
| anything under `perf/` | `PERFORMANCE.md` — scenario table, 设计意图 bullet for a new scenario, thresholds |
| `tests/test_dashboard.py` | `MOCK_TESTS.md` — it enumerates that file's scenarios one by one |
| `web/studio.html`, `web/studio/steps.js`, `studio/`, `pages/studio_*.py`, or the BDD step definitions | `STUDIO.md` — step-library table, architecture, security boundary; a new step also updates the mapping table in `MOCK_TESTS.md` if it covers a technique listed there |
| a new feature-area test file | new `bug_*` mutants + regenerated `TRIAGE.md` (§1), and the `web/bugs/` row in `README.md` |
| `docker/`, `docker-compose.yml`, `requirements.txt`, or `.github/workflows/` | `DOCKER.md` — service table, arg passing, report paths, trade-offs; a `playwright==` bump also moves the base image tag in `docker/Dockerfile` |
| a convention in this file (new rule, changed count, new trap) | `AGENTS.md` itself — including the examples above that name specific classes and scenario counts, which go stale silently |

`TRIAGE.md` is the exception: it is **generated** by `scripts/triage.py` and is
never edited by hand — a hand edit either lies about detection ability or masks
a real regression that the diff in §1 would have caught.

The copy catalogue rule (§4) is the model to follow: docs that can be derived
from code should be *recounted* from code, and docs that state numbers should
say when the numbers were measured.

---

## Verification

Run all six before reporting completion. The triage diff is not optional.

```bash
# 1. Full suite — expect zero reruns, not just zero failures
.venv/bin/python -m pytest

# 2. Mutation detection unchanged (see §1)
.venv/bin/python scripts/triage.py --write /tmp/TRIAGE_new.md
diff TRIAGE.md /tmp/TRIAGE_new.md

# 3. Convention audit — all four should report nothing (verified: they do)
grep -rn '_page\.page\.' tests/                                       # POM reach-through
grep -rnE 'assert .*(text_content|is_visible|all_text_contents)\(\)' tests/   # snapshot asserts
grep -rn 'locator("#' pages/                                          # structural selectors
grep -rn 'name="[A-Z]' pages/ | grep -v ':[0-9]*: *#'                 # hardcoded copy

# The last one filters comment lines: base_page.py documents the ladder with a
# literal get_by_role("button", name="Add") example, which is prose, not a locator.

# 4. Only if you touched perf/ or server/
perf/run_perf.sh performance -Jduration=15 -Jrampup=3

# 5. Doc sync (§7) — for each area you touched, confirm its paired doc changed
#    in this same change; if a doc states counts, recount them from the code.
git diff --stat        # code files with no matching doc row from §7? go back.

# 6. Only if you touched server/ or pages/ — the same increment gate CI runs on
#    the PR. Every line you changed there must be stained; see COVERAGE.md 六.
.venv/bin/diff-cover reports/coverage-py/coverage.xml \
    --compare-branch origin/main --fail-under 100
```

### The containerized equivalent

The same five steps run in Docker on macOS, Linux and Windows without a local
Python, browser, JDK or JMeter — see [`DOCKER.md`](DOCKER.md):

```bash
docker compose run --rm all      # steps 1, 2, 3 and 4 in one go
docker compose run --rm tests    # step 1 only
docker compose run --rm triage   # step 2 only
docker compose run --rm tests audit      # step 3 only
docker compose run --rm tests coverage   # step 6 only (needs step 1 to have run)
```

`coverage` is deliberately outside `all`: an *increment* needs a base branch to be
an increment of (`$COVERAGE_BASE`, default `origin/main`), which is the pull
request's context, not a local full self-check's.

`.github/workflows/tests.yml` runs those same commands verbatim, so a CI
failure reproduces locally with one line. The container is a convenience, not a
replacement judgement: the pass/fail bar is still the one stated above, and the
`--reruns 2` in `pytest.ini` still means "zero reruns", not "zero failures".

Two constraints the container adds:

- **The base image tag and `requirements.txt` are one version.** Bumping
  `playwright==` means bumping the `mcr.microsoft.com/playwright/python:v…` tag
  in `docker/Dockerfile` in the same change. The image's browser builds are
  numbered per Playwright release; drift makes pip install a Playwright that
  looks for a `/ms-playwright` directory the image does not have.
- **`.venv/` must stay in `.dockerignore` and masked in `docker-compose.yml`.**
  A macOS `.venv/bin/python` is a Mach-O binary, but `[ -x .venv/bin/python ]`
  in `perf/run_perf.sh` is still true inside a Linux container, so the perf run
  would pick it and die.

Front-end performance guardrails are marked `perf`; skip them with
`pytest -m "not perf"` when iterating. The linearity check in
`tests/test_frontend_perf.py` is the one that would actually catch an O(n²)
render — fixed budgets would not — so keep it if you touch that file.

## Git

Commit and push only when asked. Author commits as the repo owner; **do not add
`Co-Authored-By` or any AI attribution** — this was an explicit standing
instruction from the owner, not a one-off.
