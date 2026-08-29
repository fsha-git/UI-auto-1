#!/usr/bin/env bash
# JMeter 压测一键运行脚本。
# 用法: perf/run_perf.sh [-v] [performance|stress|stepload|spike|soak|concurrency|all] \
#         [额外 -J 参数透传给 jmeter]
#   -v  跟踪模式：打印每条执行的命令（set -x），便于排查脚本本身的问题。
# 每类测试启动全新 server 进程（注册 perf/accounts.csv 的独立压测账号，且
# todo_store 干净），跑完生成 HTML dashboard
# 并用 perf/check_jtl.py 做阈值校验；任一类失败则最终退出码非零。
# 每次运行追加一行历史到 $PERF_HISTORY（默认 reports/jmeter/history.jsonl），
# 结束时由 perf/make_dashboard.py 生成跨运行趋势看板 reports/jmeter/perf_dashboard.html。
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "${1:-}" = "-v" ]; then
    shift
    PS4='+ [${BASH_SOURCE##*/}:${LINENO}] '
    set -x
fi

TARGET="${1:-all}"
shift || true

if ! command -v jmeter >/dev/null 2>&1; then
    echo "jmeter not found. Install with: brew install jmeter" >&2
    exit 1
fi
if [ -z "${JAVA_HOME:-}" ] && [ -d /opt/homebrew/opt/openjdk@21 ]; then
    export JAVA_HOME=/opt/homebrew/opt/openjdk@21
fi

PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
PORT="${PERF_PORT:-8000}"
HISTORY="${PERF_HISTORY:-reports/jmeter/history.jsonl}"
# 压测专用账号，与 pytest 使用的 demo 账号完全分离（server/app.py 按账号分区存储）。
ACCOUNTS="${PERF_ACCOUNTS:-perf/accounts.csv}"
# 相对历史中位数的回归阈值：p95 上升或吞吐量下降超过该百分比即失败。
REGRESSION_PCT="${PERF_MAX_REGRESSION_PCT:-25}"

if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $PORT is already in use; set PERF_PORT to use another port." >&2
    exit 1
fi

case "$TARGET" in
    performance|stress|stepload|spike|soak|concurrency) TYPES=("$TARGET") ;;
    # soak 默认 30 分钟，不进 all；需要时单独跑 perf/run_perf.sh soak
    all) TYPES=(performance stress stepload spike concurrency) ;;
    *) echo "Unknown target: $TARGET (expected performance|stress|stepload|spike|soak|concurrency|all)" >&2; exit 1 ;;
esac

thresholds_for() {
    case "$1" in
        performance) echo "--max-error-rate 1 --max-p95 800 --min-throughput 50" ;;
        stress)      echo "--max-error-rate 10 --max-5xx 0" ;;
        stepload)    echo "--max-error-rate 5 --max-5xx 0" ;;
        # 尖峰期间允许排队变慢，但不允许服务端出错或拒绝
        spike)       echo "--max-error-rate 2 --max-5xx 0" ;;
        # 长稳：任何错误或吞吐塌陷都是资源泄漏的信号
        soak)        echo "--max-error-rate 0.5 --max-5xx 0 --min-throughput 40" ;;
        concurrency) echo "--max-error-rate 0 --max-5xx 0" ;;
    esac
}

SERVER_PID=""
cleanup() {
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

FAILED=()
for TYPE in "${TYPES[@]}"; do
    echo "=== $TYPE ==="
    OUT="reports/jmeter/$TYPE"
    rm -rf "$OUT"          # jmeter -e -o 拒绝非空目录
    mkdir -p "$OUT"

    "$PY" -m server --port "$PORT" --accounts "$ACCOUNTS" >"$OUT/server.log" 2>&1 &
    SERVER_PID=$!
    for _ in $(seq 1 50); do
        curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break
        sleep 0.2
    done

    JM_RC=0
    jmeter -n -t "perf/$TYPE.jmx" \
        -Jhost=127.0.0.1 -Jport="$PORT" "$@" \
        -l "$OUT/results.jtl" -j "$OUT/jmeter.log" \
        -e -o "$OUT/dashboard" || JM_RC=$?

    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    SERVER_PID=""

    CHECK_RC=0
    # 除固定阈值外，再跟同场景历史（仅统计通过的运行）的中位数比较，
    # 捕捉"绝对值仍达标但相对基线明显劣化"的回归。首次运行无基线，自动跳过。
    # shellcheck disable=SC2046
    "$PY" perf/check_jtl.py "$OUT/results.jtl" --json "$OUT/check.json" \
        $(thresholds_for "$TYPE") \
        --baseline "$HISTORY" --baseline-type "$TYPE" --max-regression-pct "$REGRESSION_PCT" \
        || CHECK_RC=$?
    if [ "$JM_RC" -ne 0 ] || [ "$CHECK_RC" -ne 0 ]; then
        FAILED+=("$TYPE")
    fi

    # 无条件记录（失败的运行也进历史，趋势图上显示为红点）
    "$PY" perf/record_run.py --type "$TYPE" --out-dir "$OUT" --history "$HISTORY" \
        --jmeter-rc "$JM_RC" --check-rc "$CHECK_RC" -- "$@" \
        || echo "warn: record_run failed for $TYPE" >&2
    echo "Dashboard: $OUT/dashboard/index.html"
    echo
done

# 失败的运行也要刷新趋势看板
"$PY" perf/make_dashboard.py --history "$HISTORY" --out reports/jmeter/perf_dashboard.html \
    || echo "warn: dashboard generation failed" >&2
echo "Perf trend dashboard: reports/jmeter/perf_dashboard.html"

if [ "${#FAILED[@]}" -gt 0 ]; then
    echo "FAILED: ${FAILED[*]}" >&2
    exit 1
fi
echo "All selected tests passed."
