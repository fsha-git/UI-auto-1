"""Demo backend: serves web/ static files plus a small JSON API.

This is the code under test for tests/test_api.py, and the coverage target
for the Python coverage report (pytest-cov). The test server fixture in
tests/conftest.py mounts DemoApiHandler in-process, so coverage of this
module is collected in the same pytest run as the UI/API tests.

Endpoints:
- GET    /api/health          -> {"status": "ok"}
- POST   /api/login           -> {"token": ...} on demo/demo123, else 401/400
- GET    /api/stats           -> canned weekly stats (used by dashboard.html)
- GET    /api/todos           -> list *the caller's* todos (requires Bearer token)
- POST   /api/todos           -> add todo (requires Bearer token, validates text)
- DELETE /api/todos/<id>      -> delete own todo (requires Bearer token)

Accounts and data isolation
---------------------------
The server supports multiple accounts, and todos are partitioned per account:
one account can neither read nor delete another's. This exists so load tests
can run under their own identities (perf/accounts.csv) instead of sharing the
single `demo` account with the functional suite — sharing one identity makes
per-user isolation bugs structurally untestable and makes concurrent runs
contend on data they should not see.
"""

import json
import threading
from http.server import SimpleHTTPRequestHandler

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"

#: username -> password. The pytest suite uses `demo`; load tests register
#: their own accounts on top of this (see register_account / load_accounts).
ACCOUNTS: dict[str, str] = {DEMO_USERNAME: DEMO_PASSWORD}

TOKEN_SUFFIX = "-session-token"


def issue_token(username: str) -> str:
    """Deterministic per-user bearer token.

    Deliberately derivable rather than random: tests/test_api.py and the JMeter
    plans need a token for an account without a prior login round-trip. A real
    service would mint an opaque, expiring session here.
    """
    return f"{username}{TOKEN_SUFFIX}"


#: Preserved name/value ("demo-session-token") — the token for the demo account.
DEMO_TOKEN = issue_token(DEMO_USERNAME)


def register_account(username: str, password: str) -> None:
    ACCOUNTS[username] = password


def load_accounts(csv_path) -> int:
    """Register `username,password` rows from a CSV (header optional).

    Used by `python -m server --accounts perf/accounts.csv` so load tests get
    dedicated identities. Returns the number of accounts registered.
    """
    import csv

    count = 0
    with open(csv_path, newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2 or row[0].strip().lower() == "username":
                continue
            register_account(row[0].strip(), row[1].strip())
            count += 1
    return count


MAX_TODO_TEXT_LENGTH = 200

# Canned response for the dashboard's default (unmocked) data source.
DEFAULT_STATS = {"labels": ["Mon", "Tue", "Wed", "Thu", "Fri"], "values": [12, 19, 3, 5, 2]}


class TodoStore:
    """In-memory, thread-safe todo store, partitioned per user.

    Ids are allocated from a single global counter rather than per user: that
    keeps perf/concurrency.jmx meaningful, since a duplicate id handed to two
    threads (the failure mode that test hunts for) stays observable.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._items: dict[str, dict[int, dict]] = {}
        self._next_id = 1

    def list(self, username: str) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._items.get(username, {}).values()]

    def add(self, username: str, text: str) -> dict:
        with self._lock:
            item = {"id": self._next_id, "text": text, "done": False, "owner": username}
            self._items.setdefault(username, {})[self._next_id] = item
            self._next_id += 1
            return dict(item)

    def delete(self, username: str, todo_id: int) -> bool:
        """Delete one of *this user's* todos. Another user's id is not found,
        so a cross-account delete is a 404 rather than a silent success."""
        with self._lock:
            return self._items.get(username, {}).pop(todo_id, None) is not None

    def reset(self):
        with self._lock:
            self._items.clear()
            self._next_id = 1


todo_store = TodoStore()


# ---------------------------------------------------------------------------
# Pure request-handling logic: (payload/args) -> (status_code, response_body)
# Kept free of HTTP plumbing so it is easy to test and easy to read in the
# coverage report.
# ---------------------------------------------------------------------------

def handle_login(payload) -> tuple[int, dict]:
    if not isinstance(payload, dict):
        return 400, {"error": "request body must be a JSON object"}
    username = payload.get("username")
    password = payload.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return 400, {"error": "username and password are required"}
    if ACCOUNTS.get(username) == password:
        return 200, {"token": issue_token(username), "username": username}
    return 401, {"error": "invalid username or password"}


def handle_get_stats() -> tuple[int, dict]:
    return 200, DEFAULT_STATS


def handle_list_todos(username: str) -> tuple[int, dict]:
    return 200, {"todos": todo_store.list(username)}


def handle_add_todo(username: str, payload) -> tuple[int, dict]:
    if not isinstance(payload, dict):
        return 400, {"error": "request body must be a JSON object"}
    text = payload.get("text")
    if not isinstance(text, str):
        return 400, {"error": "text is required and must be a string"}
    text = text.strip()
    if not text:
        return 400, {"error": "text must not be empty"}
    if len(text) > MAX_TODO_TEXT_LENGTH:
        return 400, {"error": f"text must be at most {MAX_TODO_TEXT_LENGTH} characters"}
    return 201, todo_store.add(username, text)


def handle_delete_todo(username: str, todo_id_raw: str) -> tuple[int, dict | None]:
    try:
        todo_id = int(todo_id_raw)
    except ValueError:
        return 400, {"error": "todo id must be an integer"}
    if todo_store.delete(username, todo_id):
        return 204, None
    return 404, {"error": f"todo {todo_id} not found"}


def authenticated_username(authorization_header: str | None) -> str | None:
    """Resolve a `Authorization: Bearer <token>` header to an account name,
    or None if the header is missing/malformed or names an unknown account."""
    if not isinstance(authorization_header, str):
        return None
    scheme, _, token = authorization_header.partition(" ")
    if scheme != "Bearer" or not token.endswith(TOKEN_SUFFIX):
        return None
    username = token[: -len(TOKEN_SUFFIX)]
    return username if username in ACCOUNTS else None



# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

class DemoApiHandler(SimpleHTTPRequestHandler):
    """Static file server for web/ plus the /api/* JSON endpoints above."""

    def log_message(self, format, *args):  # keep pytest output clean
        pass

    def _send_json(self, status: int, body: dict | None):
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        if data:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def _read_json(self):
        """Return the parsed JSON request body, or None if it isn't valid JSON."""
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return None

    def _require_user(self) -> str | None:
        """Return the authenticated account name, or send a 401 and return
        None. Every todo endpoint is scoped to the value this returns."""
        username = authenticated_username(self.headers.get("Authorization"))
        if username is None:
            self._send_json(401, {"error": "missing or invalid Authorization header"})
        return username

    def do_GET(self):
        if self.path == "/api/health":
            self._send_json(200, {"status": "ok"})
        elif self.path == "/api/stats":
            self._send_json(*handle_get_stats())
        elif self.path == "/api/todos":
            username = self._require_user()
            if username is not None:
                self._send_json(*handle_list_todos(username))
        elif self.path.startswith("/api/"):
            self._send_json(404, {"error": "not found"})
        else:
            super().do_GET()  # static files from web/

    def do_POST(self):
        if self.path == "/api/login":
            payload = self._read_json()
            if payload is None:
                self._send_json(400, {"error": "request body must be valid JSON"})
            else:
                self._send_json(*handle_login(payload))
        elif self.path == "/api/todos":
            username = self._require_user()
            if username is not None:
                payload = self._read_json()
                if payload is None:
                    self._send_json(400, {"error": "request body must be valid JSON"})
                else:
                    self._send_json(*handle_add_todo(username, payload))
        else:
            self._send_json(404, {"error": "not found"})

    def do_DELETE(self):
        if self.path.startswith("/api/todos/"):
            username = self._require_user()
            if username is not None:
                todo_id_raw = self.path.removeprefix("/api/todos/")
                self._send_json(*handle_delete_todo(username, todo_id_raw))
        else:
            self._send_json(404, {"error": "not found"})

    # a fake functin won't be called by front
    def fake_function(self):
        # pyrefly: ignore [division-by-zero]
        return 1/0
