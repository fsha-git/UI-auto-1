from playwright.sync_api import Page, Route

from pages.dashboard_page import DashboardPage


def test_dashboard_uses_real_backend_when_unmocked(page: Page, dashboard_url: str):
    # No route interception: exercises the server's own /api/stats endpoint.
    page.goto(dashboard_url)
    dashboard = DashboardPage(page)
    dashboard.wait_for_loaded()
    assert dashboard.bar_values() == [12, 19, 3, 5, 2]
    assert dashboard.total_value() == 41
    assert dashboard.row_count() == 5


def test_dashboard_renders_mocked_chart_data(page: Page, dashboard_url: str):
    mock_payload = {"labels": ["A", "B", "C"], "values": [10, 20, 30]}
    page.route("**/api/stats", lambda route: route.fulfill(json=mock_payload))

    page.goto(dashboard_url)
    dashboard = DashboardPage(page)
    dashboard.wait_for_loaded()
    assert dashboard.bar_values() == [10, 20, 30]
    assert dashboard.total_value() == 60
    assert dashboard.row_count() == 3


def test_dashboard_shows_empty_state_when_no_data(page: Page, dashboard_url: str):
    page.route("**/api/stats", lambda route: route.fulfill(json={"labels": [], "values": []}))

    page.goto(dashboard_url)
    dashboard = DashboardPage(page)
    dashboard.wait_for_loaded()
    assert dashboard.is_empty_visible()
    assert dashboard.bar_values() == []


def test_dashboard_shows_error_state_on_api_failure(page: Page, dashboard_url: str):
    page.route("**/api/stats", lambda route: route.fulfill(status=500, body="Internal Server Error"))

    page.goto(dashboard_url)
    dashboard = DashboardPage(page)
    dashboard.wait_for_loaded()
    assert dashboard.is_error_visible()
    assert "500" in dashboard.error_text()


def test_dashboard_refresh_button_refetches_data(page: Page, dashboard_url: str):
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

    page.goto(dashboard_url)
    dashboard = DashboardPage(page)
    dashboard.wait_for_loaded()
    assert dashboard.bar_values() == [1]

    dashboard.click_refresh()
    dashboard.wait_for_loaded()
    assert dashboard.bar_values() == [1, 2]


def test_dashboard_shows_network_error_on_aborted_request(page: Page, dashboard_url: str):
    # route.abort() simulates a connection-level failure (DNS/refused/offline),
    # distinct from an HTTP error response like 500.
    page.route("**/api/stats", lambda route: route.abort())

    page.goto(dashboard_url)
    dashboard = DashboardPage(page)
    dashboard.wait_for_loaded()
    assert dashboard.is_error_visible()
    assert "network error" in dashboard.error_text()


def test_dashboard_shows_error_on_malformed_json_response(page: Page, dashboard_url: str):
    # A 200 response whose body isn't valid JSON: response.json() throws,
    # which should be caught by the same error handling as a network failure.
    page.route(
        "**/api/stats",
        lambda route: route.fulfill(status=200, content_type="application/json", body="not valid json"),
    )

    page.goto(dashboard_url)
    dashboard = DashboardPage(page)
    dashboard.wait_for_loaded()
    assert dashboard.is_error_visible()


def test_dashboard_handles_all_zero_values_without_crashing(page: Page, dashboard_url: str):
    # values.length > 0 but every value is 0: should still render the chart
    # (not the empty state), with zero-height bars and no divide-by-zero crash.
    page.route(
        "**/api/stats",
        lambda route: route.fulfill(json={"labels": ["A", "B", "C"], "values": [0, 0, 0]}),
    )

    page.goto(dashboard_url)
    dashboard = DashboardPage(page)
    dashboard.wait_for_loaded()
    assert not dashboard.is_empty_visible()
    assert dashboard.bar_values() == [0, 0, 0]
    assert dashboard.total_value() == 0


def test_dashboard_renders_large_dataset(page: Page, dashboard_url: str):
    labels = [f"Month{i}" for i in range(1, 13)]
    values = list(range(1, 13))
    page.route("**/api/stats", lambda route: route.fulfill(json={"labels": labels, "values": values}))

    page.goto(dashboard_url)
    dashboard = DashboardPage(page)
    dashboard.wait_for_loaded()
    assert dashboard.bar_values() == values
    assert dashboard.row_count() == 12
    assert dashboard.total_value() == sum(values)


def test_dashboard_shows_loading_state_while_request_is_pending(page: Page, dashboard_url: str):
    # Capture the route without fulfilling it, so the fetch stays pending
    # until we explicitly complete it — letting us observe the loading state
    # in between deterministically, with no arbitrary sleep/race involved.
    pending = {}
    page.route("**/api/stats", lambda route: pending.__setitem__("route", route))

    page.goto(dashboard_url)
    dashboard = DashboardPage(page)
    assert dashboard.loading.is_visible()

    pending["route"].fulfill(json={"labels": ["A"], "values": [7]})
    dashboard.wait_for_loaded()
    assert dashboard.bar_values() == [7]


def test_dashboard_refresh_cycles_through_three_mock_datasets(page: Page, dashboard_url: str):
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

    page.goto(dashboard_url)
    dashboard = DashboardPage(page)
    dashboard.wait_for_loaded()
    assert dashboard.bar_values() == [1]

    dashboard.click_refresh()
    dashboard.wait_for_loaded()
    assert dashboard.bar_values() == [1, 2]

    dashboard.click_refresh()
    dashboard.wait_for_loaded()
    assert dashboard.bar_values() == [1, 2, 3]
