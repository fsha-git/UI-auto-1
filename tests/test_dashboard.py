from playwright.sync_api import Page, Route, expect

from pages.dashboard_page import DashboardPage
from tests.conftest import wait_for_intercepted_route


def test_dashboard_uses_real_backend_when_unmocked(dashboard: DashboardPage):
    # No route interception: exercises the server's own /api/stats endpoint.
    dashboard.open()
    dashboard.expect_loaded()
    dashboard.expect_bar_values([12, 19, 3, 5, 2])
    dashboard.expect_total(41)
    dashboard.expect_row_count(5)


def test_dashboard_renders_mocked_chart_data(dashboard: DashboardPage, page: Page):
    mock_payload = {"labels": ["A", "B", "C"], "values": [10, 20, 30]}
    page.route("**/api/stats", lambda route: route.fulfill(json=mock_payload))

    dashboard.open()
    dashboard.expect_loaded()
    dashboard.expect_bar_values([10, 20, 30])
    dashboard.expect_total(60)
    dashboard.expect_row_count(3)


def test_dashboard_shows_empty_state_when_no_data(dashboard: DashboardPage, page: Page):
    page.route("**/api/stats", lambda route: route.fulfill(json={"labels": [], "values": []}))

    dashboard.open()
    expect(dashboard.empty_message).to_be_visible()
    dashboard.expect_bar_values([])


def test_dashboard_shows_error_state_on_api_failure(dashboard: DashboardPage, page: Page):
    page.route("**/api/stats", lambda route: route.fulfill(status=500, body="Internal Server Error"))

    dashboard.open()
    expect(dashboard.error_message).to_be_visible()
    expect(dashboard.error_message).to_contain_text("500")


def test_dashboard_refresh_button_refetches_data(dashboard: DashboardPage, page: Page):
    responses = [
        {"labels": ["A"], "values": [1]},
        {"labels": ["A", "B"], "values": [1, 2]},
    ]
    call_count = {"n": 0}

    def handle_route(route: Route):
        payload = responses[min(call_count["n"], len(responses) - 1)]
        call_count["n"] += 1
        route.fulfill(json=payload)

    page.route("**/api/stats", handle_route)

    dashboard.open()
    dashboard.expect_loaded()
    dashboard.expect_bar_values([1])

    dashboard.click_refresh()
    dashboard.expect_loaded()
    dashboard.expect_bar_values([1, 2])


def test_dashboard_shows_network_error_on_aborted_request(dashboard: DashboardPage, page: Page):
    # route.abort() simulates a connection-level failure (DNS/refused/offline),
    # distinct from an HTTP error response like 500.
    page.route("**/api/stats", lambda route: route.abort())

    dashboard.open()
    expect(dashboard.error_message).to_be_visible()
    expect(dashboard.error_message).to_contain_text("network error")


def test_dashboard_shows_error_on_malformed_json_response(dashboard: DashboardPage, page: Page):
    # A 200 response whose body isn't valid JSON: response.json() throws,
    # which should be caught by the same error handling as a network failure.
    page.route(
        "**/api/stats",
        lambda route: route.fulfill(status=200, content_type="application/json", body="not valid json"),
    )

    dashboard.open()
    expect(dashboard.error_message).to_be_visible()


def test_dashboard_handles_all_zero_values_without_crashing(dashboard: DashboardPage, page: Page):
    # values.length > 0 but every value is 0: should still render the chart
    # (not the empty state), with zero-height bars and no divide-by-zero crash.
    page.route(
        "**/api/stats",
        lambda route: route.fulfill(json={"labels": ["A", "B", "C"], "values": [0, 0, 0]}),
    )

    dashboard.open()
    dashboard.expect_loaded()
    expect(dashboard.empty_message).to_be_hidden()
    dashboard.expect_bar_values([0, 0, 0])
    dashboard.expect_total(0)


def test_dashboard_renders_large_dataset(dashboard: DashboardPage, page: Page):
    labels = [f"Month{i}" for i in range(1, 13)]
    values = list(range(1, 13))
    page.route("**/api/stats", lambda route: route.fulfill(json={"labels": labels, "values": values}))

    dashboard.open()
    dashboard.expect_loaded()
    dashboard.expect_bar_values(values)
    dashboard.expect_row_count(12)
    dashboard.expect_total(sum(values))


def test_dashboard_shows_loading_state_while_request_is_pending(dashboard: DashboardPage, page: Page):
    # Capture the route without fulfilling it, so the fetch stays pending
    # until we explicitly complete it — letting us observe the loading state
    # in between deterministically, with no arbitrary sleep/race involved.
    pending = {}
    page.route("**/api/stats", lambda route: pending.__setitem__("route", route))

    dashboard.open()
    route = wait_for_intercepted_route(page, pending)
    expect(dashboard.loading).to_be_visible()

    route.fulfill(json={"labels": ["A"], "values": [7]})
    dashboard.expect_loaded()
    dashboard.expect_bar_values([7])


def test_dashboard_refresh_cycles_through_three_mock_datasets(dashboard: DashboardPage, page: Page):
    responses = [
        {"labels": ["A"], "values": [1]},
        {"labels": ["A", "B"], "values": [1, 2]},
        {"labels": ["A", "B", "C"], "values": [1, 2, 3]},
    ]
    call_count = {"n": 0}

    def handle_route(route: Route):
        payload = responses[min(call_count["n"], len(responses) - 1)]
        call_count["n"] += 1
        route.fulfill(json=payload)

    page.route("**/api/stats", handle_route)

    dashboard.open()
    dashboard.expect_loaded()
    dashboard.expect_bar_values([1])

    dashboard.click_refresh()
    dashboard.expect_loaded()
    dashboard.expect_bar_values([1, 2])

    dashboard.click_refresh()
    dashboard.expect_loaded()
    dashboard.expect_bar_values([1, 2, 3])
