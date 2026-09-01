"""Test-side reader for the low-code step vocabulary the Studio page uses.

Exactly the same trick as pages/i18n.py, for exactly the same reason: the
Gherkin sentence of a step is written in ONE place -- web/studio/steps.js --
and read from there by every consumer, so a reworded step cannot drift
between the palette, the generated .feature, and the pytest-bdd step
definition that has to match it.

The catalogue is a .js file rather than .json so web/studio.html can load it
with a plain <script> tag (no fetch, so no window in which the palette is
empty while a locator is already looking for it). Its object literal is
strict JSON, which is what lets this module parse it without duplicating the
data or introducing a build step.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

STEPS_PATH = Path(__file__).resolve().parent.parent / "web" / "studio" / "steps.js"

#: The three swimlanes of the timeline canvas: who acts at this point in time.
LANES = ("mock", "browser", "assert")
KEYWORDS = ("Given", "When", "Then")

_ASSIGNMENT = re.compile(r"window\.STUDIO_STEPS\s*=\s*(\{.*\});", re.DOTALL)
#: pytest-bdd parse syntax: {name} for a string, {name:d} for an integer.
_PLACEHOLDER = re.compile(r"\{(\w+)(?::\w+)?\}")


@lru_cache(maxsize=1)
def load_steps() -> dict[str, dict]:
    source = STEPS_PATH.read_text(encoding="utf-8")
    match = _ASSIGNMENT.search(source)
    if match is None:
        raise RuntimeError(f"no window.STUDIO_STEPS assignment found in {STEPS_PATH}")
    return json.loads(match.group(1))


def step_ids() -> list[str]:
    """Every step id, in palette order (JSON preserves key order)."""
    return list(load_steps())


def step(step_id: str) -> dict:
    """Look up one step. Raises on an unknown id rather than falling back
    silently -- the same rule as pages.i18n.t(), and for the same reason: a
    typo here would otherwise surface much later as a step definition that
    mysteriously never matches."""
    steps = load_steps()
    try:
        return steps[step_id]
    except KeyError:
        raise KeyError(
            f"unknown studio step {step_id!r}; known: {', '.join(steps)}"
        ) from None


def step_template(step_id: str) -> str:
    """The Gherkin sentence, still in parse syntax.

    This is what the pytest-bdd step definitions pass to parsers.parse(), so
    the template genuinely has a single definition site.
    """
    return step(step_id)["template"]


def step_param_names(step_id: str) -> list[str]:
    """Parameter names in template order, read off the template itself."""
    return _PLACEHOLDER.findall(step_template(step_id))


def render_step(step_id: str, params: dict[str, object] | None = None) -> str:
    """The Gherkin sentence with its placeholders substituted.

    Used by studio/runner.py to write the .feature file, and mirrored in
    JavaScript by the Studio page's live preview.
    """
    params = params or {}
    values = {}
    for spec in step(step_id)["params"]:
        name = spec["name"]
        raw = params.get(name, spec["default"])
        if spec["type"] == "int":
            try:
                values[name] = str(int(str(raw).strip()))
            except ValueError:
                raise ValueError(
                    f"step {step_id!r} parameter {name!r} must be an integer, got {raw!r}"
                ) from None
        else:
            values[name] = str(raw)
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], step_template(step_id))
