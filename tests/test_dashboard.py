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
