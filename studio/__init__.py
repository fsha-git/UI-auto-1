"""Low-code Mock Scenario Studio: the backend behind web/studio.html.

This package is *tooling*, deliberately kept outside server/app.py:

- server/app.py is the application under test. Its endpoint surface is what
  the JMeter plans in perf/ baseline, and AGENTS.md §6 requires a new endpoint
  there to come with its own scenario. The Studio's /studio/api/* endpoints
  exist to *run* tests, are never load-tested, and would only pollute that
  baseline — so they live on a StudioHandler subclass instead, and
  server/app.py is untouched.
- The one process still serves web/ (so studio.html, dashboard.html and the
  /api/* endpoints all share an origin), because the scenarios it runs drive
  the real demo app.

Run it with:  python -m studio --port 8100
"""
