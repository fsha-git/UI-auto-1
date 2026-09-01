Feature: Dashboard mock scenarios

  These scenarios are the low-code Studio's committed examples: each one was
  assembled on the timeline canvas of web/studio.html and saved here, and each
  one now runs in the daily `pytest` suite like any hand-written test. The
  step vocabulary is web/studio/steps.js; the implementations live in
  tests/test_dashboard_bdd.py and go through pages/dashboard_page.py.

  # The step ORDER is the assertion here: the loading indicator can only be
  # observed while the request is still in flight, so "held pending" has to
  # come before the navigation and the release has to come after the check.
  Scenario: The loading state stays visible until the pending request is released
    Given the /api/stats endpoint is held pending
    When I open the dashboard
    Then the loading indicator is visible
    When I release the pending /api/stats request with labels "A" and values "7"
    And I wait for the dashboard to finish loading
    Then the chart bars are "7"
    And the total is 7

  Scenario: Refreshing twice walks through three datasets in order
    Given the /api/stats endpoint returns the dataset sequence "A=1 | A,B=1,2 | A,B,C=1,2,3"
    When I open the dashboard
    And I wait for the dashboard to finish loading
    Then the chart bars are "1"
    When I click the Refresh button
    And I wait for the dashboard to finish loading
    Then the chart bars are "1,2"
    When I click the Refresh button
    And I wait for the dashboard to finish loading
    Then the chart bars are "1,2,3"
    And the table has 3 rows
    And the total is 6

  Scenario: A failing endpoint surfaces its status code
    Given the /api/stats endpoint returns HTTP status 500
    When I open the dashboard
    Then an error message is shown
    And the error message contains "500"

  Scenario: An empty payload renders the empty state and no bars
    Given the /api/stats endpoint returns no data
    When I open the dashboard
    Then the empty-data message is visible
    And the chart renders no bars
