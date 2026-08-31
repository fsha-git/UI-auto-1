"""Front-end JS coverage ("code staining") for the inline scripts in web/*.html.

While UI tests run, a CDP session per page turns on V8's precise coverage
(Profiler.startPreciseCoverage). At test teardown the collected ranges are
folded into per-script character bitmaps:

    0 = never reported by V8 (whitespace/comments outside any range)
    1 = reported but never executed  -> stained red
    2 = executed at least once       -> stained green

Bitmaps are merged (max) across all tests in the session, and at session end
an HTML report is written with each script's source colored line by line,
plus per-file and overall coverage percentages.

Inline scripts are identified by (page path, startLine, startColumn) from
Debugger.scriptParsed, which lets us slice the exact script text back out of
the HTML file on disk. V8 coverage offsets are relative to that script text.
"""

import html as html_module
from pathlib import Path
from urllib.parse import urlparse

SEEN = 1
EXECUTED = 2


class ScriptRecord:
    def __init__(self, rel_path: str, start_line: int, source: str):
        self.rel_path = rel_path
        self.start_line = start_line  # 0-based line in the HTML file
        self.source = source
        self.state = bytearray(len(source))  # 0/SEEN/EXECUTED per character

    def apply_ranges(self, ranges: list[tuple[int, int, int]]):
        """Apply (start, end, count) ranges. Sorted outer-first so that inner
        (block-level) ranges override the enclosing function's range, matching
        V8's nesting semantics."""
        length = len(self.source)
        take_state = bytearray(length)
        for start, end, count in sorted(ranges, key=lambda r: (r[0], -r[1])):
            start = max(0, min(start, length))
            end = max(0, min(end, length))
            if start >= end:
                continue
            value = EXECUTED if count > 0 else SEEN
            take_state[start:end] = bytes([value]) * (end - start)
        # Merge into the session-wide bitmap: executed anywhere wins.
        self.state = bytearray(max(a, b) for a, b in zip(self.state, take_state))

    def stats(self) -> tuple[int, int]:
        """(executed, executable) counted over non-whitespace characters."""
        executed = executable = 0
        for ch, st in zip(self.source, self.state):
            if st == 0 or ch.isspace():
                continue
            executable += 1
            if st == EXECUTED:
                executed += 1
        return executed, executable


class JsCoverageCollector:
    def __init__(self, server_url: str, web_dir: Path):
        self.server_url = server_url.rstrip("/")
        self.web_dir = web_dir
        self.scripts: dict[tuple, ScriptRecord] = {}

    # -- collection ---------------------------------------------------------

    def start(self, page):
        """Attach a CDP session to the page and turn on precise coverage.
        Returns an opaque session object to pass back to collect()."""
        cdp = page.context.new_cdp_session(page)
        parsed: dict[str, dict] = {}
        cdp.on("Debugger.scriptParsed", lambda params: parsed.__setitem__(params["scriptId"], params))
        cdp.send("Debugger.enable")
        cdp.send("Profiler.enable")
        cdp.send("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True})
        return cdp, parsed

    def collect_all(self, sessions):
        """Take precise coverage from every session, then detach them all.

        Sessions from one test must be collected together because of two V8
        subtleties around same-process pages (a window.open popup or a
        target=_blank tab shares its opener's renderer, hence its isolate):

        - ``Profiler.takePreciseCoverage`` drains the *isolate's* pending
          coverage, so whichever session takes first receives the entries for
          every same-process page — and a later take (or a detach happening
          before another session's take) leaves nothing for the rest.
        - Each session's ``Debugger.scriptParsed`` stream only describes its
          own page's scripts.

        So the coverage entries are resolved against the union of every
        session's scriptParsed metadata. Script ids are only unique within
        one isolate, so the union is keyed by (scriptId, url) — two isolates
        reusing an id for different scripts stay distinct entries instead of
        overwriting each other, and a lookup only matches metadata whose URL
        agrees with the coverage entry's.
        """
        combined_meta: dict[tuple[str, str], dict] = {}
        for _, parsed in sessions:
            for script_id, meta in parsed.items():
                combined_meta[(script_id, meta.get("url", ""))] = meta

        for session in sessions:
            cdp, parsed = session
            try:
                result = cdp.send("Profiler.takePreciseCoverage")
            except Exception:
                continue  # page/context already closed — nothing to collect
            for entry in result.get("result", []):
                meta = parsed.get(entry["scriptId"])
                if meta is None:
                    meta = combined_meta.get((entry["scriptId"], entry.get("url", "")))
                    if meta is None:
                        continue
                record = self._record_for(meta)
                if record is None:
                    continue
                ranges = [
                    (r["startOffset"], r["endOffset"], r["count"])
                    for fn in entry.get("functions", [])
                    for r in fn.get("ranges", [])
                ]
                record.apply_ranges(ranges)

        for cdp, _ in sessions:
            try:
                cdp.detach()
            except Exception:
                pass  # page/context already closed — nothing to detach

    def collect(self, session):
        self.collect_all([session])

    def _record_for(self, meta: dict) -> ScriptRecord | None:
        """Map a scriptParsed event to a ScriptRecord, slicing the inline
        script's source out of the HTML file it lives in."""
        url = meta.get("url", "")
        if not url.startswith(self.server_url):
            return None
        rel_path = urlparse(url).path.lstrip("/")
        key = (rel_path, meta["startLine"], meta["startColumn"])
        if key in self.scripts:
            return self.scripts[key]

        file_path = self.web_dir / rel_path
        if not file_path.is_file():
            return None
        lines = file_path.read_text().splitlines(keepends=True)
        start_line, start_col = meta["startLine"], meta["startColumn"]
        end_line, end_col = meta["endLine"], meta["endColumn"]
        if end_line >= len(lines):
            return None
        chunk = lines[start_line:end_line + 1]
        chunk[-1] = chunk[-1][:end_col]
        chunk[0] = chunk[0][start_col:]
        record = ScriptRecord(rel_path, start_line, "".join(chunk))
        self.scripts[key] = record
        return record

    # -- reporting ----------------------------------------------------------

    def write_report(self, out_dir: Path) -> Path | None:
        if not self.scripts:
            return None
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "index.html"
        out_path.write_text(self._render_report())
        return out_path

    def _render_report(self) -> str:
        records = sorted(self.scripts.values(), key=lambda r: (r.rel_path, r.start_line))
        total_executed = sum(r.stats()[0] for r in records)
        total_executable = sum(r.stats()[1] for r in records)
        overall = _percent(total_executed, total_executable)

        summary_rows = []
        sections = []
        for i, record in enumerate(records):
            executed, executable = record.stats()
            pct = _percent(executed, executable)
            name = f"{record.rel_path} — &lt;script&gt; @ line {record.start_line + 1}"
            summary_rows.append(
                f'<tr><td><a href="#script-{i}">{name}</a></td>'
                f"<td>{executed} / {executable}</td>"
                f'<td><div class="pctbar"><div style="width:{pct:.1f}%"></div></div> {pct:.1f}%</td></tr>'
            )
            sections.append(
                f'<section id="script-{i}"><h2>{name} <small>{pct:.1f}% covered</small></h2>'
                f"<pre>{self._render_source(record)}</pre></section>"
            )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>JS Coverage — web/ inline scripts</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; max-width: 960px; margin: 0 auto; padding: 32px 16px;
         background: #fff; color: #1a1a1a; }}
  h1 {{ font-size: 22px; }}
  h2 {{ font-size: 16px; margin-top: 32px; }}
  h2 small {{ color: #666; font-weight: normal; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #ddd; font-size: 14px; }}
  .pctbar {{ display: inline-block; width: 120px; height: 10px; background: #f3c2c8; vertical-align: middle; }}
  .pctbar div {{ height: 100%; background: #57ab5a; }}
  pre {{ background: #fafafa; border: 1px solid #ddd; border-radius: 6px; padding: 12px; overflow-x: auto;
        font-size: 13px; line-height: 1.5; }}
  .lineno {{ color: #999; user-select: none; }}
  .hit {{ background: #ccf2cc; }}
  .miss {{ background: #ffc9cf; }}
  .legend span {{ padding: 2px 8px; margin-right: 8px; font-size: 13px; }}
</style>
</head>
<body>
<h1>JS Coverage Report — inline scripts in web/</h1>
<p>Overall: <strong>{overall:.1f}%</strong> ({total_executed} / {total_executable} executable characters),
merged across all UI tests in this pytest session.</p>
<p class="legend"><span class="hit">executed</span><span class="miss">never executed</span>
<span>unstained = not reported by V8 (whitespace / comments)</span></p>
<table>
<thead><tr><th>Script</th><th>Executed / executable chars</th><th>Coverage</th></tr></thead>
<tbody>{"".join(summary_rows)}</tbody>
</table>
{"".join(sections)}
</body>
</html>
"""

    def _render_source(self, record: ScriptRecord) -> str:
        out = []
        line_no = record.start_line + 1
        line_start = True
        # Emit runs of consecutive characters sharing the same coverage state,
        # split at newlines so each line gets its HTML-file line number.
        run_chars: list[str] = []
        run_state = None

        def flush():
            nonlocal run_chars, run_state
            if not run_chars:
                return
            text = html_module.escape("".join(run_chars))
            if run_state == EXECUTED:
                out.append(f'<span class="hit">{text}</span>')
            elif run_state == SEEN:
                out.append(f'<span class="miss">{text}</span>')
            else:
                out.append(text)
            run_chars = []

        for ch, st in zip(record.source, record.state):
            if line_start:
                flush()
                out.append(f'<span class="lineno">{line_no:>4} </span>')
                line_start = False
            if ch == "\n":
                flush()
                out.append("\n")
                line_no += 1
                line_start = True
                continue
            if st != run_state:
                flush()
                run_state = st
            run_chars.append(ch)
        flush()
        return "".join(out)


def _percent(executed: int, executable: int) -> float:
    return 100.0 * executed / executable if executable else 100.0
