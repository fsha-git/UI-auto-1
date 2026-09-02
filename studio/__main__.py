"""Launcher for the Mock Scenario Studio: `python -m studio --port 8100`.

Binds loopback by default and refuses anything else without --i-know: this
process runs pytest on request, so it must not be reachable from the network.
"""

import argparse
import sys

from studio.server import PortInUseError, serve


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m studio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument(
        "--i-know",
        action="store_true",
        help="allow binding a non-loopback host (this process executes pytest; "
        "exposing it to the network hands out remote code execution).",
    )
    args = parser.parse_args()

    if args.host not in ("127.0.0.1", "localhost", "::1") and not args.i_know:
        parser.error(f"refusing to bind {args.host}; pass --i-know if you really mean it")

    try:
        serve(host=args.host, port=args.port)
    except PortInUseError as exc:
        sys.exit(f"python -m studio: {exc}")


if __name__ == "__main__":
    main()
