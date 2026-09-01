from playwright.sync_api import Locator, Page, expect

from pages.base_page import BasePage
from pages.i18n import DEFAULT_LOCALE, t
from pages.studio_steps import render_step, step_param_names


class StudioPage(BasePage):
    """The low-code Mock Scenario Studio (web/studio.html).

    Owns every piece of DOM knowledge about the step palette, the timeline
    canvas, the Gherkin preview and the run-result panel, so tests describe
    scenarios ("add this step, move it up, run") rather than selectors.
    """

    PATH = "studio.html"

    def __init__(self, page: Page, base_url: str = "", locale: str = DEFAULT_LOCALE):
        super().__init__(page, base_url, locale)
        # Tier 1 -- role + accessible name (see the policy in base_page.py).
        self.run_btn = page.get_by_role("button", name=t("studioRun", locale))
        self.clear_btn = page.get_by_role("button", name=t("studioClear", locale))
        self.save_btn = page.get_by_role("button", name=t("studioSaveFeature", locale))
        self.open_trace_btn = page.get_by_role("button", name=t("studioOpenTrace", locale))
        self.run_selected_btn = page.get_by_role("button", name=t("studioRunSelected", locale))
        self.compose_tab = page.get_by_role("button", name=t("studioTabCompose", locale))
        self.suite_tab = page.get_by_role("button", name=t("studioTabSuite", locale))

        # Tier 2 -- label. The input has no role+name of its own worth binding
        # to (its placeholder would be the weaker source), but it carries a
        # real <label for=...>.
        self.scenario_name_input = page.get_by_label(t("studioScenarioName", locale))

        # Tier 3 -- no accessible name available, so tier 1 does not apply:
        # unnamed <ol>/<ul> containers, a <pre>, and status <span>s.
        self.timeline = page.get_by_test_id("timeline")
        self.timeline_steps = page.get_by_test_id("timeline-step")
        self.timeline_sentences = page.get_by_test_id("timeline-sentence")
        self.timeline_statuses = page.get_by_test_id("timeline-status")
        self.gherkin_preview = page.get_by_test_id("gherkin-preview")
        self.run_status = page.get_by_test_id("run-status")
        self.run_error = page.get_by_test_id("run-error")
        self.run_command = page.get_by_test_id("run-command")
        self.run_output = page.get_by_test_id("run-output")
        self.test_results = page.get_by_test_id("test-result")
        self.trace_path = page.get_by_test_id("trace-path")
        self.report_link = page.get_by_test_id("report-link")
        self.save_result = page.get_by_test_id("save-result")
        self.suite_list = page.get_by_test_id("suite-list")

    # --- palette -----------------------------------------------------------

    def palette_step(self, step_id: str) -> Locator:
        """Tier 3: one palette entry, anchored by a per-step test id.

        A shared test id plus a `[data-step-id=...]` CSS filter would work too,
        but a purpose-built anchor per entry keeps this off tier 4 entirely.
        """
        return self.page.get_by_test_id(f"palette-step-{step_id}")

    def add_step(self, step_id: str, **params: object) -> "StudioPage":
        """Fill a palette entry's parameters and push it onto the timeline.

        Parameter names come from pages/studio_steps.py — the same catalogue
        the page builds the inputs from — so nothing about the step's shape is
        duplicated here.
        """
        entry = self.palette_step(step_id)
        for name in step_param_names(step_id):
            if name in params:
                # Tier 2, scoped: each input is named by its own <label>.
                entry.get_by_label(name).fill(str(params[name]))
        entry.get_by_role("button", name=t("studioAddStep", self.locale)).click()
        return self

    # --- timeline ----------------------------------------------------------

    def move_step_up(self, index: int) -> "StudioPage":
        self._step_button(index, "studioMoveUp").click()
        return self

    def move_step_down(self, index: int) -> "StudioPage":
        self._step_button(index, "studioMoveDown").click()
        return self

    def remove_step(self, index: int) -> "StudioPage":
        self._step_button(index, "studioRemoveStep").click()
        return self

    def _step_button(self, index: int, copy_key: str) -> Locator:
        # Tier 1, scoped to one timeline card.
        return self.timeline_steps.nth(index).get_by_role(
            "button", name=t(copy_key, self.locale)
        )

    def clear(self) -> "StudioPage":
        self.clear_btn.click()
        return self

    def set_scenario_name(self, name: str) -> "StudioPage":
        self.scenario_name_input.fill(name)
        return self

    # --- running -----------------------------------------------------------

    def run(self) -> "StudioPage":
        self.run_btn.click()
        return self

    def save_feature(self) -> "StudioPage":
        self.save_btn.click()
        return self

    def open_suite_tab(self) -> "StudioPage":
        self.suite_tab.click()
        return self

    def select_suite_test(self, name: str) -> "StudioPage":
        # Tier 1, scoped: each checkbox is named by its wrapping label, whose
        # text is the pytest node id the runner API reported.
        self.suite_list.get_by_role("checkbox", name=name).check()
        return self

    def run_selected(self) -> "StudioPage":
        self.run_selected_btn.click()
        return self

    # --- assertion helpers -------------------------------------------------

    def expect_timeline(self, step_ids: list[str]) -> None:
        """Assert the timeline holds exactly these steps, in this order.

        Compares the rendered sentences rather than the ids, so a step whose
        parameters were dropped or whose order was lost both fail here.
        """
        expect(self.timeline_steps).to_have_count(len(step_ids))
        for index, step_id in enumerate(step_ids):
            expect(self.timeline_steps.nth(index)).to_have_attribute("data-step-id", step_id)

    def expect_rendered_step(self, index: int, step_id: str, **params: object) -> None:
        """Assert one card shows the step's sentence with its parameters
        substituted, using the same renderer the backend writes the .feature
        with (pages/studio_steps.render_step)."""
        expect(self.timeline_sentences.nth(index)).to_have_text(render_step(step_id, params))

    def expect_gherkin_contains(self, text: str) -> None:
        expect(self.gherkin_preview).to_contain_text(text)

    def expect_gherkin_excludes(self, text: str) -> None:
        expect(self.gherkin_preview).not_to_contain_text(text)

    def expect_step_statuses(self, statuses: list[str]) -> None:
        """Assert the per-step result lights, in timeline order."""
        expect(self.timeline_statuses).to_have_count(len(statuses))
        for index, status in enumerate(statuses):
            expect(self.timeline_statuses.nth(index)).to_have_attribute("data-status", status)

    def expect_run_status(self, status: str) -> None:
        expect(self.run_status).to_have_attribute("data-status", status)

    def expect_test_outcomes(self, outcomes: list[str]) -> None:
        """Assert the per-test result rows, in the order pytest reported them.

        This is the only evidence a "run existing mock tests" run produces on
        the page — that mode has no timeline to light up.
        """
        expect(self.test_results).to_have_count(len(outcomes))
        for index, outcome in enumerate(outcomes):
            expect(self.test_results.nth(index)).to_have_attribute("data-outcome", outcome)
