#!/usr/bin/env bash
# JMeter 压测一键运行脚本。
# 用法: perf/run_perf.sh [performance|stress|concurrency|all] [额外 -J 参数透传给 jmeter]
# 每类测试启动全新 server 进程（保证 todo_store 干净），跑完生成 HTML dashboard
# 并用 perf/check_jtl.py 做阈值校验；任一类失败则最终退出码非零。
set -euo pipefail

cd "$(dirname "$0")/.."

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

if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $PORT is already in use; set PERF_PORT to use another port." >&2
    exit 1
fi

case "$TARGET" in
    performance|stress|concurrency) TYPES=("$TARGET") ;;
    all) TYPES=(performance stress concurrency) ;;
    *) echo "Unknown target: $TARGET (expected performance|stress|concurrency|all)" >&2; exit 1 ;;
esac

thresholds_for() {
    case "$1" in
        performance) echo "--max-error-rate 1 --max-p95 800" ;;
        stress)      echo "--max-error-rate 10 --max-5xx 0" ;;
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

    "$PY" -m server --port "$PORT" >"$OUT/server.log" 2>&1 &
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
    # shellcheck disable=SC2046
    "$PY" perf/check_jtl.py "$OUT/results.jtl" $(thresholds_for "$TYPE") || CHECK_RC=$?
    if [ "$JM_RC" -ne 0 ] || [ "$CHECK_RC" -ne 0 ]; then
        FAILED+=("$TYPE")
    fi
    echo "Dashboard: $OUT/dashboard/index.html"
    echo
done

if [ "${#FAILED[@]}" -gt 0 ]; then
    echo "FAILED: ${FAILED[*]}" >&2
    exit 1
fi
echo "All selected tests passed."
