"""Test-side reader for the copy catalogue the pages themselves use.

Locators built on role + accessible name bind to visible copy. Keeping that
copy in one file -- web/i18n/catalog.js, read here and by the browser -- means
renaming a button is a one-line change instead of a silent suite breakage.

The catalogue is a .js file rather than .json so the pages can load it with a
plain <script> tag (no fetch, so no window in which the text is not yet
applied). Its object literal is strict JSON, which is what lets this module
parse it without duplicating the data or introducing a build step.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "web" / "i18n" / "catalog.js"
DEFAULT_LOCALE = "en"

_ASSIGNMENT = re.compile(r"window\.I18N_CATALOGS\s*=\s*(\{.*\});", re.DOTALL)


@lru_cache(maxsize=1)
def load_catalogs() -> dict[str, dict[str, str]]:
    source = CATALOG_PATH.read_text(encoding="utf-8")
    match = _ASSIGNMENT.search(source)
    if match is None:
        raise RuntimeError(f"no window.I18N_CATALOGS assignment found in {CATALOG_PATH}")
    return json.loads(match.group(1))


def locales() -> list[str]:
    return sorted(load_catalogs())


def t(key: str, locale: str = DEFAULT_LOCALE) -> str:
    """Look up one string. Raises on an unknown key or locale rather than
    falling back silently -- a typo here would otherwise surface much later as
    a locator that mysteriously matches nothing."""
    catalogs = load_catalogs()
    if locale not in catalogs:
        raise KeyError(f"unknown locale {locale!r}; known: {', '.join(sorted(catalogs))}")
    try:
        return catalogs[locale][key]
    except KeyError:
        raise KeyError(
            f"unknown copy key {key!r} for locale {locale!r}; "
            f"known: {', '.join(sorted(catalogs[locale]))}"
        ) from None
