"""Demo backend: serves web/ static files plus a small JSON API.

This is the code under test for tests/test_api.py, and the coverage target
for the Python coverage report (pytest-cov). The test server fixture in
tests/conftest.py mounts DemoApiHandler in-process, so coverage of this
module is collected in the same pytest run as the UI/API tests.

Endpoints:
- GET    /api/health          -> {"status": "ok"}
- POST   /api/login           -> {"token": ...} on demo/demo123, else 401/400
- GET    /api/stats           -> canned weekly stats (used by dashboard.html)
- GET    /api/todos           -> list todos (requires Bearer token)
- POST   /api/todos           -> add todo (requires Bearer token, validates text)
- DELETE /api/todos/<id>      -> delete todo (requires Bearer token)
"""

import json
import threading
from http.server import SimpleHTTPRequestHandler

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"
DEMO_TOKEN = "demo-session-token"

MAX_TODO_TEXT_LENGTH = 200

# Canned response for the dashboard's default (unmocked) data source.
DEFAULT_STATS = {"labels": ["Mon", "Tue", "Wed", "Thu", "Fri"], "values": [12, 19, 3, 5, 2]}


class TodoStore:
    """In-memory, thread-safe todo store (the server handler is threaded)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}
        self._next_id = 1

    def list(self):
        with self._lock:
            return [dict(item) for item in self._items.values()]

    def add(self, text: str) -> dict:
        with self._lock:
            item = {"id": self._next_id, "text": text, "done": False}
            self._items[self._next_id] = item
            self._next_id += 1
            return dict(item)

    def delete(self, todo_id: int) -> bool:
        with self._lock:
            return self._items.pop(todo_id, None) is not None

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
    if username == DEMO_USERNAME and password == DEMO_PASSWORD:
        return 200, {"token": DEMO_TOKEN, "username": username}
    return 401, {"error": "invalid username or password"}


def handle_get_stats() -> tuple[int, dict]:
    return 200, DEFAULT_STATS


def handle_list_todos() -> tuple[int, dict]:
    return 200, {"todos": todo_store.list()}


def handle_add_todo(payload) -> tuple[int, dict]:
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
    return 201, todo_store.add(text)


def handle_delete_todo(todo_id_raw: str) -> tuple[int, dict | None]:
    try:
        todo_id = int(todo_id_raw)
    except ValueError:
        return 400, {"error": "todo id must be an integer"}
    if todo_store.delete(todo_id):
        return 204, None
    return 404, {"error": f"todo {todo_id} not found"}


def is_authorized(authorization_header: str | None) -> bool:
    return authorization_header == f"Bearer {DEMO_TOKEN}"


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

    def _require_auth(self) -> bool:
        if is_authorized(self.headers.get("Authorization")):
            return True
        self._send_json(401, {"error": "missing or invalid Authorization header"})
        return False

    def do_GET(self):
        if self.path == "/api/health":
            self._send_json(200, {"status": "ok"})
        elif self.path == "/api/stats":
            self._send_json(*handle_get_stats())
        elif self.path == "/api/todos":
            if self._require_auth():
                self._send_json(*handle_list_todos())
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
            if self._require_auth():
                payload = self._read_json()
                if payload is None:
                    self._send_json(400, {"error": "request body must be valid JSON"})
                else:
                    self._send_json(*handle_add_todo(payload))
        else:
            self._send_json(404, {"error": "not found"})

    def do_DELETE(self):
        if self.path.startswith("/api/todos/"):
            if self._require_auth():
                todo_id_raw = self.path.removeprefix("/api/todos/")
                self._send_json(*handle_delete_todo(todo_id_raw))
        else:
            self._send_json(404, {"error": "not found"})
