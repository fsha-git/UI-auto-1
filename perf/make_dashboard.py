"""Render the cross-run perf trend dashboard from history.jsonl.

Reads the JSONL run history appended by perf/record_run.py and writes a fully
self-contained HTML page (inline CSS + SVG, no JS, no CDN) that works over
file://: per-type summary cards, throughput / p95+p99 / error-rate trend
charts, and a per-run detail list. Named make_* so pytest never collects it.
"""

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TYPE_ORDER = ["performance", "stress", "stepload", "spike", "soak", "concurrency", "profile"]
TYPE_TITLES = {
    "performance": "性能基线 (performance)",
    "stress": "压力 (stress)",
    "concurrency": "并发 (concurrency)",
    "stepload": "阶梯加压 (stepload)",
    "spike": "尖峰 (spike)",
    "soak": "稳定性 (soak)",
    "profile": "个人资料只读 (profile)",
}

BLUE = "#4a7dfc"
ORANGE = "#f0a030"
RED = "#b00020"
GREEN = "#2f9e44"
MUTED = "#666"

# 图表几何（viewBox 坐标）
W, H = 640, 220
ML, MR, MT, MB = 52, 14, 14, 34  # 边距：左侧留 y 轴标签，底部留 x 轴时间


def load_history(path: Path) -> list[dict]:
    runs: list[dict] = []
    if not path.exists():
        return runs
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            print(f"warn: {path}:{lineno} is not valid JSON, skipped", file=sys.stderr)
            continue
        if not isinstance(rec, dict) or rec.get("schema", 1) > 1:
            print(f"warn: {path}:{lineno} has unknown schema, skipped", file=sys.stderr)
            continue
        runs.append(rec)
    runs.sort(key=lambda r: r.get("epoch", 0))
    return runs


def group_by_type(runs: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for run in runs:
        grouped.setdefault(run.get("type", "unknown"), []).append(run)
    ordered = {t: grouped.pop(t) for t in TYPE_ORDER if t in grouped}
    ordered.update(grouped)  # 未知类型排最后
    return ordered


def esc(value) -> str:
    return html.escape(str(value))


def fmt_params(run: dict) -> str:
    params = run.get("params") or {}
    return ", ".join(f"{k}={v}" for k, v in params.items()) or "-"


def metric(run: dict, key: str):
    metrics = run.get("metrics")
    return metrics.get(key) if isinstance(metrics, dict) else None


def fmt_num(value, unit: str = "", digits: int = 1) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        value = round(value, digits)
        if value == int(value):
            value = int(value)
    return f"{value}{unit}"


def svg_trend(runs: list[dict], series: list[tuple[str, str, str]], unit: str) -> str:
    """One trend chart. series = [(metrics key, color, legend label)]."""
    n = len(runs)
    plot_w = W - ML - MR
    plot_h = H - MT - MB
    values = [metric(r, key) for key, _, _ in series for r in runs]
    numeric = [v for v in values if isinstance(v, (int, float))]
    y_max = max(numeric) if numeric else 1
    y_max = y_max * 1.1 or 1  # 顶部留 10% 空隙；全 0 时避免除零

    def x_at(i: int) -> float:
        return ML + (plot_w / 2 if n == 1 else i * plot_w / (n - 1))

    def y_at(v: float) -> float:
        return MT + plot_h - v / y_max * plot_h

    parts = [
        f'<svg viewBox="0 0 {W} {H}" role="img" '
        f'style="width:100%;max-width:{W}px;font-family:Arial,sans-serif">'
    ]
    # 网格线 + y 轴标签
    for frac in (0.0, 0.5, 1.0):
        gy = MT + plot_h - frac * plot_h
        label = y_max * frac
        label_text = f"{label:.2f}" if y_max < 10 else f"{label:.0f}"
        parts.append(
            f'<line x1="{ML}" y1="{gy:.1f}" x2="{W - MR}" y2="{gy:.1f}" stroke="#eee"/>'
            f'<text x="{ML - 6}" y="{gy + 4:.1f}" text-anchor="end" font-size="10" '
            f'fill="{MUTED}">{label_text}</text>'
        )
    # x 轴时间标签（最多 6 个，避免重叠）
    step = max(1, -(-n // 6))
    for i in range(0, n, step):
        ts = runs[i].get("ts", "")
        short = ts[5:16].replace("T", " ") if len(ts) >= 16 else ts
        parts.append(
            f'<text x="{x_at(i):.1f}" y="{H - 8}" text-anchor="middle" '
            f'font-size="10" fill="{MUTED}">{esc(short)}</text>'
        )
    for key, color, _ in series:
        points = [(i, metric(r, key)) for i, r in enumerate(runs)]
        line = " ".join(
            f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in points if isinstance(v, (int, float))
        )
        if line.count(" ") >= 1:
            parts.append(f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2"/>')
        for i, v in points:
            run = runs[i]
            failed = not run.get("pass", False)
            if not isinstance(v, (int, float)):
                # 指标缺失（如 jmeter 崩溃）：底部画红叉占位
                cx, cy = x_at(i), MT + plot_h
                parts.append(
                    f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" font-size="12" '
                    f'fill="{RED}">×<title>{esc(run.get("ts", ""))} 指标缺失（运行异常）</title></text>'
                )
                continue
            fill = "#fff" if failed else color
            stroke = RED if failed else color
            tip = (
                f'{run.get("ts", "")}  {fmt_num(v, unit, 2)}\n'
                f'参数: {fmt_params(run)}\n'
                f'{"通过" if run.get("pass") else "失败"}'
            )
            parts.append(
                f'<circle cx="{x_at(i):.1f}" cy="{y_at(v):.1f}" r="4" fill="{fill}" '
                f'stroke="{stroke}" stroke-width="2"><title>{esc(tip)}</title></circle>'
            )
    parts.append("</svg>")
    legend = " ".join(
        f'<span class="legend"><span class="dot" style="background:{color}"></span>{esc(label)}</span>'
        for _, color, label in series
    )
    return f'<div class="chart">{legend}{"".join(parts)}</div>'


def badge(ok: bool) -> str:
    if ok:
        return f'<span class="badge" style="background:{GREEN}">通过</span>'
    return f'<span class="badge" style="background:{RED}">失败</span>'


def summary_card(run_type: str, latest: dict) -> str:
    return f"""
<div class="card">
  <h3>{esc(TYPE_TITLES.get(run_type, run_type))} {badge(latest.get("pass", False))}</h3>
  <p class="muted">{esc(latest.get("ts", "-"))} · {esc(fmt_params(latest))}</p>
  <div class="kpis">
    <div><b>{esc(fmt_num(metric(latest, "throughput")))}</b><span>req/s</span></div>
    <div><b>{esc(fmt_num(metric(latest, "p95_ms")))}</b><span>p95 ms</span></div>
    <div><b>{esc(fmt_num(metric(latest, "error_rate"), digits=2))}</b><span>错误率 %</span></div>
    <div><b>{esc(fmt_num(metric(latest, "samples")))}</b><span>样本数</span></div>
  </div>
</div>"""


def labels_table(run: dict) -> str:
    labels = run.get("labels")
    if not isinstance(labels, dict) or not labels:
        return '<p class="muted">无 statistics.json 数据</p>'
    rows = []
    keys = sorted(labels, key=lambda k: (k == "Total", k))  # Total 放最后
    for name in keys:
        s = labels[name]
        if not isinstance(s, dict):
            continue
        rows.append(
            f"<tr><td>{esc(name)}</td>"
            f'<td>{esc(fmt_num(s.get("sampleCount")))}</td>'
            f'<td>{esc(fmt_num(s.get("errorPct"), digits=2))}%</td>'
            f'<td>{esc(fmt_num(s.get("medianResTime")))}</td>'
            f'<td>{esc(fmt_num(s.get("pct2ResTime")))}</td>'
            f'<td>{esc(fmt_num(s.get("pct3ResTime")))}</td>'
            f'<td>{esc(fmt_num(s.get("throughput")))}</td></tr>'
        )
    return (
        "<table><thead><tr><th>请求</th><th>样本</th><th>错误率</th>"
        "<th>p50 ms</th><th>p95 ms</th><th>p99 ms</th><th>req/s</th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def run_details(run: dict, is_latest: bool) -> str:
    metrics = run.get("metrics") or {}
    thresholds = metrics.get("thresholds") or {}
    failures = metrics.get("failures") or []
    if is_latest:
        report = f'<a href="{esc(run.get("type", ""))}/dashboard/index.html">JMeter 报告</a>'
    else:
        report = '<span class="muted">原始报告已被后续运行覆盖</span>'
    failure_html = (
        f'<p style="color:{RED}">失败原因: {esc("; ".join(str(f) for f in failures))}</p>'
        if failures else ""
    )
    overrides = run.get("overrides") or {}
    override_note = f'（覆盖: {esc(", ".join(f"{k}={v}" for k, v in overrides.items()))}）' if overrides else ""
    return f"""
<details>
  <summary>{esc(run.get("ts", "-"))} {badge(run.get("pass", False))}
    <span class="muted">{esc(fmt_params(run))} · 吞吐 {esc(fmt_num(metric(run, "throughput")))} req/s
    · p95 {esc(fmt_num(metric(run, "p95_ms")))} ms
    · 错误率 {esc(fmt_num(metric(run, "error_rate"), digits=2))}%</span></summary>
  <div class="detail-body">
    <p>参数: {esc(fmt_params(run))} {override_note} · 阈值:
      {esc(", ".join(f"{k}={v}" for k, v in thresholds.items() if v is not None) or "无")}
      · jmeter_rc={esc(run.get("jmeter_rc", "-"))} check_rc={esc(run.get("check_rc", "-"))}
      · {report}</p>
    {failure_html}
    <p>samples={esc(fmt_num(metrics.get("samples")))} errors={esc(fmt_num(metrics.get("errors")))}
      5xx={esc(fmt_num(metrics.get("server_5xx")))}
      mean={esc(fmt_num(metrics.get("mean_ms")))}ms p50={esc(fmt_num(metrics.get("p50_ms")))}ms
      p95={esc(fmt_num(metrics.get("p95_ms")))}ms p99={esc(fmt_num(metrics.get("p99_ms")))}ms
      max={esc(fmt_num(metrics.get("max_ms")))}ms · {esc(fmt_num(metrics.get("wall_s")))}s</p>
    {labels_table(run)}
  </div>
</details>"""


def type_section(run_type: str, runs: list[dict]) -> str:
    charts = (
        "<h3>吞吐量趋势</h3>"
        + svg_trend(runs, [("throughput", BLUE, "吞吐量 (req/s)")], " req/s")
        + "<h3>延迟分位趋势</h3>"
        + svg_trend(runs, [("p95_ms", BLUE, "p95 (ms)"), ("p99_ms", ORANGE, "p99 (ms)")], " ms")
        + "<h3>错误率趋势</h3>"
        + svg_trend(runs, [("error_rate", RED, "错误率 (%)")], " %")
    )
    details = "".join(run_details(r, r is runs[-1]) for r in reversed(runs))
    return f"""
<section>
  <h2>{esc(TYPE_TITLES.get(run_type, run_type))}<span class="muted"> · 共 {len(runs)} 次运行</span></h2>
  {charts}
  <h3>历次运行</h3>
  {details}
</section>"""


def render(runs: list[dict], history_path: Path) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not runs:
        body = '<section><p class="muted">暂无历史数据 — 先运行 perf/run_perf.sh</p></section>'
    else:
        grouped = group_by_type(runs)
        cards = "".join(summary_card(t, rs[-1]) for t, rs in grouped.items())
        sections = "".join(type_section(t, rs) for t, rs in grouped.items())
        body = f'<div class="cards">{cards}</div>{sections}'
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>性能趋势看板</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: Arial, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 16px; color: #222; background: #fff; }}
  h1 {{ font-size: 24px; }}
  h2 {{ font-size: 18px; border-bottom: 1px solid #ddd; padding-bottom: 6px; }}
  h3 {{ font-size: 14px; margin: 18px 0 6px; }}
  section {{ border: 1px solid #ddd; border-radius: 6px; padding: 16px; margin: 16px 0; }}
  .muted {{ color: {MUTED}; font-weight: normal; font-size: 12px; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 12px; }}
  .card {{ flex: 1 1 200px; border: 1px solid #ddd; border-radius: 6px; padding: 12px; }}
  .card h3 {{ margin: 0 0 4px; }}
  .kpis {{ display: flex; gap: 16px; margin-top: 8px; }}
  .kpis div {{ display: flex; flex-direction: column; }}
  .kpis b {{ font-size: 18px; }}
  .kpis span {{ color: {MUTED}; font-size: 11px; }}
  .badge {{ color: #fff; border-radius: 4px; padding: 1px 6px; font-size: 11px; vertical-align: middle; }}
  .chart {{ margin: 4px 0 12px; }}
  .legend {{ font-size: 11px; color: {MUTED}; margin-right: 12px; }}
  .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 4px; margin-right: 4px; }}
  details {{ border: 1px solid #eee; border-radius: 4px; padding: 6px 10px; margin: 6px 0; }}
  summary {{ cursor: pointer; font-size: 13px; }}
  .detail-body {{ font-size: 12px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 12px; margin-top: 6px; }}
  th, td {{ text-align: left; padding: 4px 8px; border-bottom: 1px solid #eee; }}
  th {{ color: {MUTED}; font-weight: normal; }}
  a {{ color: {BLUE}; }}
</style>
</head>
<body>
<h1>性能趋势看板</h1>
<p class="muted">生成时间 {esc(generated)} · 数据源 {esc(str(history_path))} · 由 perf/run_perf.sh 自动更新</p>
{body}
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", default=str(ROOT / "reports/jmeter/history.jsonl"))
    parser.add_argument("--out", default=str(ROOT / "reports/jmeter/perf_dashboard.html"))
    args = parser.parse_args()

    history_path = Path(args.history)
    runs = load_history(history_path)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(runs, history_path))
    print(f"Wrote {out.resolve()} ({len(runs)} runs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
