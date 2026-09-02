// Single source of truth for the low-code step vocabulary of the Mock Scenario
// Studio (web/studio.html). Consumed by FOUR sides:
//
//   - the browser, via web/studio.html (step palette + Gherkin preview)
//   - the page objects, via pages/studio_steps.py
//   - the pytest-bdd step definitions, via pages/studio_steps.step_template()
//     -- so a Gherkin sentence is written exactly once, never mirrored
//   - the studio backend renderer, via studio/runner.py
//
// This mirrors web/i18n/catalog.js on purpose: a .js file loaded with a plain
// <script> tag (no fetch, so no window in which the palette is not yet
// populated), whose object literal is *strict JSON* so pages/studio_steps.py
// can parse it with json.loads and will fail loudly otherwise. No comments,
// no trailing commas, no single quotes inside the braces.
//
// Each entry:
//   keyword   Gherkin keyword. Stays literal English -- it is syntax, not UI
//             copy, so it deliberately does NOT live in web/i18n/catalog.js.
//   lane      which actor owns the step, for the timeline swimlanes:
//             "mock" (the intercepted /api/stats endpoint), "browser" (the
//             user driving dashboard.html), "assert" (the expectation).
//   template  the Gherkin sentence, in pytest-bdd `parsers.parse` syntax:
//             {name} for a string, {name:d} for an integer.
//   params    the inputs the studio renders, in template order.
//
// Key order is meaningful: it is the order the palette renders in.
window.STUDIO_STEPS = {
  "g_no_mock": {
    "keyword": "Given",
    "lane": "mock",
    "template": "the /api/stats endpoint is not mocked",
    "params": []
  },
  "g_mock_data": {
    "keyword": "Given",
    "lane": "mock",
    "template": "the /api/stats endpoint returns labels \"{labels}\" and values \"{values}\"",
    "params": [
      {"name": "labels", "type": "text", "default": "A,B,C", "hint": "comma-separated labels"},
      {"name": "values", "type": "text", "default": "10,20,30", "hint": "comma-separated integers"}
    ]
  },
  "g_mock_empty": {
    "keyword": "Given",
    "lane": "mock",
    "template": "the /api/stats endpoint returns no data",
    "params": []
  },
  "g_mock_status": {
    "keyword": "Given",
    "lane": "mock",
    "template": "the /api/stats endpoint returns HTTP status {status:d}",
    "params": [
      {"name": "status", "type": "int", "default": "500", "hint": "HTTP status code"}
    ]
  },
  "g_mock_aborted": {
    "keyword": "Given",
    "lane": "mock",
    "template": "the /api/stats endpoint aborts the connection",
    "params": []
  },
  "g_mock_malformed": {
    "keyword": "Given",
    "lane": "mock",
    "template": "the /api/stats endpoint returns the malformed body \"{body}\"",
    "params": [
      {"name": "body", "type": "text", "default": "not valid json", "hint": "a 200 body that is not JSON"}
    ]
  },
  "g_mock_pending": {
    "keyword": "Given",
    "lane": "mock",
    "template": "the /api/stats endpoint is held pending",
    "params": []
  },
  "g_mock_sequence": {
    "keyword": "Given",
    "lane": "mock",
    "template": "the /api/stats endpoint returns the dataset sequence \"{datasets}\"",
    "params": [
      {"name": "datasets", "type": "text", "default": "A=1 | A,B=1,2 | A,B,C=1,2,3", "hint": "labels=values, one dataset per | "}
    ]
  },
  "w_open_dashboard": {
    "keyword": "When",
    "lane": "browser",
    "template": "I open the dashboard",
    "params": []
  },
  "w_click_refresh": {
    "keyword": "When",
    "lane": "browser",
    "template": "I click the Refresh button",
    "params": []
  },
  "w_release_pending": {
    "keyword": "When",
    "lane": "browser",
    "template": "I release the pending /api/stats request with labels \"{labels}\" and values \"{values}\"",
    "params": [
      {"name": "labels", "type": "text", "default": "A", "hint": "comma-separated labels"},
      {"name": "values", "type": "text", "default": "7", "hint": "comma-separated integers"}
    ]
  },
  "w_wait_loaded": {
    "keyword": "When",
    "lane": "browser",
    "template": "I wait for the dashboard to finish loading",
    "params": []
  },
  "t_bars": {
    "keyword": "Then",
    "lane": "assert",
    "template": "the chart bars are \"{values}\"",
    "params": [
      {"name": "values", "type": "text", "default": "10,20,30", "hint": "comma-separated integers"}
    ]
  },
  "t_no_bars": {
    "keyword": "Then",
    "lane": "assert",
    "template": "the chart renders no bars",
    "params": []
  },
  "t_total": {
    "keyword": "Then",
    "lane": "assert",
    "template": "the total is {total:d}",
    "params": [
      {"name": "total", "type": "int", "default": "60", "hint": "expected sum"}
    ]
  },
  "t_rows": {
    "keyword": "Then",
    "lane": "assert",
    "template": "the table has {count:d} rows",
    "params": [
      {"name": "count", "type": "int", "default": "3", "hint": "expected row count"}
    ]
  },
  "t_empty_visible": {
    "keyword": "Then",
    "lane": "assert",
    "template": "the empty-data message is visible",
    "params": []
  },
  "t_empty_hidden": {
    "keyword": "Then",
    "lane": "assert",
    "template": "the empty-data message is hidden",
    "params": []
  },
  "t_error_visible": {
    "keyword": "Then",
    "lane": "assert",
    "template": "an error message is shown",
    "params": []
  },
  "t_error_contains": {
    "keyword": "Then",
    "lane": "assert",
    "template": "the error message contains \"{text}\"",
    "params": [
      {"name": "text", "type": "text", "default": "500", "hint": "substring of the error copy"}
    ]
  },
  "t_loading_visible": {
    "keyword": "Then",
    "lane": "assert",
    "template": "the loading indicator is visible",
    "params": []
  }
};
