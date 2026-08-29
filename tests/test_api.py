"""Pure API tests against the demo backend (server/app.py), using Playwright's
APIRequestContext — no browser involved. The server runs in-process (see the
demo_server fixture), so these tests also drive the Python coverage numbers
for server/app.py."""

from pathlib import Path

import pytest
from playwright.sync_api import APIRequestContext

from server.app import (
    ACCOUNTS,
    DEMO_USERNAME,
    DEMO_TOKEN,
    MAX_TODO_TEXT_LENGTH,
    issue_token,
    load_accounts,
    register_account,
    todo_store,
)

AUTH_HEADERS = {"Authorization": f"Bearer {DEMO_TOKEN}"}


@pytest.fixture(autouse=True)
def reset_todo_store():
    """The todo store lives in this pytest process; reset it around each test
    so API tests are order-independent."""
    todo_store.reset()
    yield
    todo_store.reset()


# -- health / stats ---------------------------------------------------------

def test_health_check(api_request_context: APIRequestContext):
    response = api_request_context.get("/api/health")
    assert response.status == 200
    assert response.json() == {"status": "ok"}


def test_stats_returns_labels_and_values_of_equal_length(api_request_context: APIRequestContext):
    response = api_request_context.get("/api/stats")
    assert response.status == 200
    data = response.json()
    assert len(data["labels"]) == len(data["values"]) > 0
    assert all(isinstance(v, int) for v in data["values"])


def test_unknown_api_path_returns_404(api_request_context: APIRequestContext):
    response = api_request_context.get("/api/nope")
    assert response.status == 404


def test_post_to_unknown_api_path_returns_404(api_request_context: APIRequestContext):
    response = api_request_context.post("/api/nope", data={})
    assert response.status == 404


# -- login ------------------------------------------------------------------

def test_login_with_valid_credentials_returns_token(api_request_context: APIRequestContext):
    response = api_request_context.post("/api/login", data={"username": "demo", "password": "demo123"})
    assert response.status == 200
    body = response.json()
    assert body["token"] == DEMO_TOKEN
    assert body["username"] == "demo"


def test_login_with_wrong_password_returns_401(api_request_context: APIRequestContext):
    response = api_request_context.post("/api/login", data={"username": "demo", "password": "wrong"})
    assert response.status == 401
    assert "invalid" in response.json()["error"]


def test_login_with_missing_fields_returns_400(api_request_context: APIRequestContext):
    response = api_request_context.post("/api/login", data={"username": "demo"})
    assert response.status == 400


def test_login_with_non_json_body_returns_400(api_request_context: APIRequestContext):
    # Raw bytes are sent as-is (a str would be JSON-serialized by Playwright).
    response = api_request_context.post(
        "/api/login", data=b"not json", headers={"Content-Type": "application/json"}
    )
    assert response.status == 400


def test_login_with_non_object_json_body_returns_400(api_request_context: APIRequestContext):
    response = api_request_context.post("/api/login", data=["demo", "demo123"])
    assert response.status == 400


# -- todos: auth ------------------------------------------------------------

@pytest.mark.parametrize("headers", [None, {"Authorization": "Bearer wrong-token"}])
def test_todos_require_valid_bearer_token(api_request_context: APIRequestContext, headers):
    response = api_request_context.get("/api/todos", headers=headers)
    assert response.status == 401


def test_delete_todo_requires_auth(api_request_context: APIRequestContext):
    response = api_request_context.delete("/api/todos/1")
    assert response.status == 401


# -- todos: CRUD ------------------------------------------------------------

def test_todo_list_is_initially_empty(api_request_context: APIRequestContext):
    response = api_request_context.get("/api/todos", headers=AUTH_HEADERS)
    assert response.status == 200
    assert response.json() == {"todos": []}


def test_added_todo_appears_in_list(api_request_context: APIRequestContext):
    created = api_request_context.post("/api/todos", data={"text": "write API tests"}, headers=AUTH_HEADERS)
    assert created.status == 201
    todo = created.json()
    assert todo["text"] == "write API tests"
    assert todo["done"] is False

    listed = api_request_context.get("/api/todos", headers=AUTH_HEADERS)
    assert listed.json()["todos"] == [todo]


def test_added_todos_get_unique_incrementing_ids(api_request_context: APIRequestContext):
    ids = [
        api_request_context.post("/api/todos", data={"text": f"task {i}"}, headers=AUTH_HEADERS).json()["id"]
        for i in range(3)
    ]
    assert ids == sorted(set(ids))


def test_add_todo_trims_surrounding_whitespace(api_request_context: APIRequestContext):
    response = api_request_context.post("/api/todos", data={"text": "  spaced  "}, headers=AUTH_HEADERS)
    assert response.status == 201
    assert response.json()["text"] == "spaced"


@pytest.mark.parametrize(
    "payload",
    [
        {},                    # text missing
        {"text": ""},          # empty
        {"text": "   "},       # whitespace only
        {"text": 123},         # wrong type
        {"text": "x" * (MAX_TODO_TEXT_LENGTH + 1)},  # too long
    ],
)
def test_add_todo_rejects_invalid_text(api_request_context: APIRequestContext, payload):
    response = api_request_context.post("/api/todos", data=payload, headers=AUTH_HEADERS)
    assert response.status == 400
    assert "error" in response.json()


def test_add_todo_with_non_object_json_body_returns_400(api_request_context: APIRequestContext):
    response = api_request_context.post("/api/todos", data=["a", "b"], headers=AUTH_HEADERS)
    assert response.status == 400


def test_add_todo_with_non_json_body_returns_400(api_request_context: APIRequestContext):
    response = api_request_context.post(
        "/api/todos", data=b"{broken", headers={**AUTH_HEADERS, "Content-Type": "application/json"}
    )
    assert response.status == 400


def test_delete_existing_todo_removes_it(api_request_context: APIRequestContext):
    todo = api_request_context.post("/api/todos", data={"text": "delete me"}, headers=AUTH_HEADERS).json()

    deleted = api_request_context.delete(f"/api/todos/{todo['id']}", headers=AUTH_HEADERS)
    assert deleted.status == 204

    listed = api_request_context.get("/api/todos", headers=AUTH_HEADERS)
    assert listed.json() == {"todos": []}


def test_delete_missing_todo_returns_404(api_request_context: APIRequestContext):
    response = api_request_context.delete("/api/todos/999", headers=AUTH_HEADERS)
    assert response.status == 404


def test_delete_with_non_integer_id_returns_400(api_request_context: APIRequestContext):
    response = api_request_context.delete("/api/todos/abc", headers=AUTH_HEADERS)
    assert response.status == 400


def test_delete_on_non_todo_path_returns_404(api_request_context: APIRequestContext):
    response = api_request_context.delete("/api/stats", headers=AUTH_HEADERS)
    assert response.status == 404


# -- multi-account data isolation -------------------------------------------
# The load tests run under their own accounts (perf/accounts.csv) rather than
# sharing `demo`. These tests are what make that separation worth having:
# they pin the per-account partitioning that the sharing used to hide.

OTHER_USERNAME = "other-user"
OTHER_PASSWORD = "other-pass"


@pytest.fixture
def other_account():
    """A second registered account, torn down after the test."""
    register_account(OTHER_USERNAME, OTHER_PASSWORD)
    yield {"Authorization": f"Bearer {issue_token(OTHER_USERNAME)}"}
    ACCOUNTS.pop(OTHER_USERNAME, None)


def test_each_account_logs_in_to_its_own_token(api_request_context: APIRequestContext, other_account):
    response = api_request_context.post(
        "/api/login", data={"username": OTHER_USERNAME, "password": OTHER_PASSWORD}
    )
    assert response.status == 200
    assert response.json()["token"] == issue_token(OTHER_USERNAME)
    assert response.json()["token"] != DEMO_TOKEN


def test_token_of_an_unregistered_account_is_rejected(api_request_context: APIRequestContext):
    response = api_request_context.get(
        "/api/todos", headers={"Authorization": f"Bearer {issue_token('ghost')}"}
    )
    assert response.status == 401


def test_todos_are_not_visible_across_accounts(api_request_context: APIRequestContext, other_account):
    api_request_context.post("/api/todos", data={"text": "demo's todo"}, headers=AUTH_HEADERS)

    listed = api_request_context.get("/api/todos", headers=other_account)
    assert listed.status == 200
    assert listed.json() == {"todos": []}


def test_account_cannot_delete_another_accounts_todo(
    api_request_context: APIRequestContext, other_account
):
    todo = api_request_context.post(
        "/api/todos", data={"text": "not yours"}, headers=AUTH_HEADERS
    ).json()

    # A cross-account delete must not silently succeed.
    forbidden = api_request_context.delete(f"/api/todos/{todo['id']}", headers=other_account)
    assert forbidden.status == 404

    still_there = api_request_context.get("/api/todos", headers=AUTH_HEADERS)
    assert still_there.json()["todos"] == [todo]


def test_todo_ids_stay_unique_across_accounts(api_request_context: APIRequestContext, other_account):
    # Ids come from one global counter, so perf/concurrency.jmx can still
    # detect a duplicate id handed to two threads.
    mine = api_request_context.post("/api/todos", data={"text": "a"}, headers=AUTH_HEADERS).json()
    theirs = api_request_context.post("/api/todos", data={"text": "b"}, headers=other_account).json()
    assert mine["id"] != theirs["id"]
    assert mine["owner"] != theirs["owner"]


# -- account registration ---------------------------------------------------

def test_load_accounts_registers_csv_rows_and_skips_the_header(tmp_path):
    csv_path = tmp_path / "accounts.csv"
    csv_path.write_text("username,password\nloaded1,pw1\nloaded2,pw2\n")
    try:
        assert load_accounts(csv_path) == 2
        assert ACCOUNTS["loaded1"] == "pw1"
        assert ACCOUNTS["loaded2"] == "pw2"
        # the built-in demo account is added to, never replaced
        assert DEMO_USERNAME in ACCOUNTS
    finally:
        ACCOUNTS.pop("loaded1", None)
        ACCOUNTS.pop("loaded2", None)


def test_load_accounts_ignores_blank_and_short_rows(tmp_path):
    csv_path = tmp_path / "accounts.csv"
    csv_path.write_text("username,password\n\nincomplete\ngood,pw\n")
    try:
        assert load_accounts(csv_path) == 1
        assert ACCOUNTS["good"] == "pw"
    finally:
        ACCOUNTS.pop("good", None)


def test_ships_with_dedicated_load_test_accounts():
    """perf/accounts.csv is what keeps the load tests off the demo account."""
    accounts_csv = Path(__file__).resolve().parent.parent / "perf" / "accounts.csv"
    assert accounts_csv.exists(), "perf/accounts.csv is required by perf/run_perf.sh"
    rows = [line for line in accounts_csv.read_text().splitlines()[1:] if line.strip()]
    assert len(rows) >= 50
    assert all(not row.startswith(f"{DEMO_USERNAME},") for row in rows)
