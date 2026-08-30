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

**`web/bugs/*.html` are 11 frozen mutants of `web/demo.html`, each carrying one
injected defect. `scripts/triage.py` runs `tests/test_demo.py` against every one
of them and records which tests catch which bug in `TRIAGE.md`.**

```bash
.venv/bin/python scripts/triage.py --write /tmp/TRIAGE_new.md
diff TRIAGE.md /tmp/TRIAGE_new.md      # MUST be empty
```

A non-empty diff means your change silently weakened the suite's ability to
detect real defects. That is the most expensive kind of regression in a test
framework, and nothing else you did matters until it is fixed.

Two rules follow:

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

The mutants are older copies that predate the auth gate and the logout button.
That is expected; they only need to support `tests/test_demo.py`.

---

## 2. Locators: a strict priority ladder

Defined once, in `pages/base_page.py`. Every locator takes the **highest tier
actually available for that element**, and says in a comment when it falls back.

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
- **`DashboardPage.error_message` is tier 1 with a caveat.** That paragraph is
  `display:none` until a request fails, so it is absent from the accessibility
  tree and `get_by_role("alert")` resolves to **zero** elements in the default
  and success states. Assertions of the form "it appeared / it says X" are fine
  (`expect()` retries into them). To assert that *no* error is shown, use
  `to_have_count(0)` — `to_be_hidden()` would also pass if the element were
  deleted outright.

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

Six plans in `perf/`, each answering a different question: `performance`
(baseline load), `stepload` (capacity knee — each level held long enough to
read, unlike a linear ramp), `spike` (recovery after a burst), `soak` (drift and
leaks; excluded from `all` because it defaults to 30 min), `stress` (linear
ramp), `concurrency` (rendezvous correctness). `stepload` uses four stock thread
groups with staggered delays — **do not introduce a jmeter-plugins dependency.**

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
- Absolute perf numbers do not extrapolate: the load generator shares a machine
  with the service over loopback, and `ThreadingHTTPServer` is itself the
  bottleneck. This suite's value is **relative** — trends, concurrency
  correctness, regression gating. `PERFORMANCE.md` states this; keep it stated.

---

## Verification

Run all four before reporting completion. The triage diff is not optional.

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
```

Front-end performance guardrails are marked `perf`; skip them with
`pytest -m "not perf"` when iterating. The linearity check in
`tests/test_frontend_perf.py` is the one that would actually catch an O(n²)
render — fixed budgets would not — so keep it if you touch that file.

## Git

Commit and push only when asked. Author commits as the repo owner; **do not add
`Co-Authored-By` or any AI attribution** — this was an explicit standing
instruction from the owner, not a one-off.
