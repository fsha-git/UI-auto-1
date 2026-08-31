"""Trend-chart UI tests: the multi-series canvas line chart on demo.html,
its hover tooltip, legend toggles, and the seeded data regeneration.

Kept out of tests/test_demo.py on purpose: scripts/triage.py runs this file
against the bug_chart_* mutants only (see SUITE_FOR_PREFIX), the same way
tests/test_windows.py owns the bug_win_* group.

Canvas pixels cannot be located, so every assertion goes through the DOM
mirror contract documented in web/demo.html: hidden chart-point nodes with
data-series/-index/-value/-px/-py, the data-* attributes on the tooltip, and
data-series-count / data-generation on the canvas itself.
"""

from pages.demo_page import DemoPage

SERIES = ("chartSeriesVisits", "chartSeriesSales", "chartSeriesErrors")
POINTS_PER_SERIES = 12

# With the chart's fixed seed (42) every errors-series point sits >15 CSS px
# from any visits/sales point, so hovering a toggled-off errors point can
# never accidentally capture a still-visible neighbour (hit radius is 10 px).
# Index 0 has the largest clearance (~54 px).
SAFE_HIDDEN_POINT = ("chartSeriesErrors", 0)


# -- rendering ---------------------------------------------------------------

def test_chart_renders_all_series(demo_page: DemoPage):
    demo_page.expect_legend_series(len(SERIES))
    demo_page.expect_visible_series_count(len(SERIES))
    for series_key in SERIES:
        demo_page.expect_point_count(series_key, POINTS_PER_SERIES)


# -- hover tooltip -----------------------------------------------------------

def test_hover_point_shows_tooltip_with_its_value(demo_page: DemoPage):
    demo_page.hover_chart_point("chartSeriesVisits", 3)
    demo_page.expect_tooltip_for("chartSeriesVisits", 3)


def test_tooltip_follows_to_a_point_in_another_series(demo_page: DemoPage):
    demo_page.hover_chart_point("chartSeriesVisits", 3)
    demo_page.expect_tooltip_for("chartSeriesVisits", 3)
    demo_page.hover_chart_point("chartSeriesSales", 8)
    demo_page.expect_tooltip_for("chartSeriesSales", 8)


def test_tooltip_hides_on_mouse_leave(demo_page: DemoPage):
    demo_page.hover_chart_point("chartSeriesSales", 5)
    demo_page.expect_tooltip_for("chartSeriesSales", 5)
    demo_page.leave_chart()
    demo_page.expect_tooltip_hidden()


# -- legend toggles ----------------------------------------------------------

def test_legend_toggle_removes_series_from_chart_and_hit_test(demo_page: DemoPage):
    hidden_series, hidden_index = SAFE_HIDDEN_POINT
    demo_page.toggle_series(hidden_series)
    demo_page.expect_visible_series_count(len(SERIES) - 1)
    # The mirror still carries the toggled-off points (that is part of the
    # contract), but hovering one must no longer produce a tooltip.
    demo_page.expect_point_count(hidden_series, POINTS_PER_SERIES)
    demo_page.hover_chart_point(hidden_series, hidden_index)
    demo_page.expect_tooltip_hidden()

    demo_page.toggle_series(hidden_series)
    demo_page.expect_visible_series_count(len(SERIES))
    demo_page.hover_chart_point(hidden_series, hidden_index)
    demo_page.expect_tooltip_for(hidden_series, hidden_index)


# -- data regeneration -------------------------------------------------------

def test_regenerate_produces_a_new_dataset(demo_page: DemoPage):
    demo_page.expect_chart_generation(1)
    demo_page.regenerate_chart()
    demo_page.expect_chart_generation(2)
    # The tooltip must agree with the *regenerated* mirror: hover_chart_point
    # re-reads the fresh data-px/-py, and expect_tooltip_for re-reads the
    # fresh data-value.
    demo_page.hover_chart_point("chartSeriesVisits", 0)
    demo_page.expect_tooltip_for("chartSeriesVisits", 0)
