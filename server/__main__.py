"""Standalone launcher so external tools (e.g. JMeter) can target a fixed port.

The pytest fixture in tests/conftest.py builds its own in-process server on an
ephemeral port; this module reuses the exact same handler wiring but binds a
known address: `python -m server --port 8000`.
"""

import argparse
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from server.app import ACCOUNTS, DemoApiHandler, load_accounts

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class KeepAliveHandler(DemoApiHandler):
    # HTTP/1.1 so load-test clients can reuse connections; without it every
    # request opens a fresh socket and the client exhausts ephemeral ports.
    # Safe because every response path sends Content-Length.
    protocol_version = "HTTP/1.1"


class LoadTestServer(ThreadingHTTPServer):
    # Default accept backlog (5) drops connections under bursts of
    # simultaneous connects; raise it for load runs.
    request_queue_size = 128


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--accounts",
        default=None,
        help="CSV of username,password rows to register in addition to the "
        "built-in demo account (see perf/accounts.csv). Load tests use these "
        "so they never share an identity with the functional suite.",
    )
    args = parser.parse_args()

    if args.accounts:
        registered = load_accounts(args.accounts)
        print(f"Registered {registered} account(s) from {args.accounts}", flush=True)
    print(f"Accounts available: {len(ACCOUNTS)}", flush=True)

    handler = partial(KeepAliveHandler, directory=str(WEB_DIR))
    httpd = LoadTestServer((args.host, args.port), handler)
    print(f"Serving on http://{args.host}:{httpd.server_port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main()
