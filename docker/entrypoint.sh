#!/usr/bin/env bash
# 容器里的任务分发器。第一个参数是任务名；其余参数透传给该任务底下的命令。
#
#   pytest [pytest 参数...]   全量 pytest 套件
#   triage                    30 个变异体的检测能力回归，等价于 AGENTS.md 验证第 2 步
#   audit                     AGENTS.md 验证第 3 步的四条约定 grep
#   perf   [场景 | -J 参数...] JMeter 压测，等价于 perf/run_perf.sh（需要 perf 镜像）
#   all                       上面四项依次跑完，不中途退出，最后汇总
#
# 首个参数不是任务名时有两种去向（见文件末尾的分发逻辑）：认得出是可执行文件就
# 原样执行（逃生口，如 `docker compose run --rm tests bash`），否则整串参数交给
# $DEFAULT_TASK —— 这样 `docker compose run --rm tests tests/test_api.py` 和
# `docker compose run --rm perf performance -Jduration=15` 都是符合直觉的写法。
set -euo pipefail

cd /work

# --- 预检 ----------------------------------------------------------------
# 报告、trace、.auth/state.json 都写在仓库根下。绑定挂载 + 不匹配的 UID 会让
# 这些写入在测试跑到一半时才失败，报出与真实原因毫不相干的错。提前挡住。
if ! touch .docker-write-check 2>/dev/null; then
    cat >&2 <<'MSG'
error: /work 不可写。

绑定挂载的属主是宿主机上的你，而容器正以另一个 UID 运行。Linux 宿主机上请带上
自己的 UID/GID 再跑：

    HOST_UID=$(id -u) HOST_GID=$(id -g) docker compose run --rm tests

详见 DOCKER.md。
MSG
    exit 1
fi
rm -f .docker-write-check

# --- 各任务 --------------------------------------------------------------

task_pytest() {
    # PYTEST_ARGS 走 eval，好让 `-m "not perf"` 这种带引号的参数保持成一个词。
    local -a extra=()
    if [ -n "${PYTEST_ARGS:-}" ]; then
        eval "extra=(${PYTEST_ARGS})"
    fi
    python -m pytest "${extra[@]}" "$@"
}

task_triage() {
    # AGENTS.md §1：变异检测能力是这个仓库最重要的不变量。重新生成一份报告，
    # 与提交在库里的 TRIAGE.md 比对，diff 非空即为回归。
    local generated=/tmp/TRIAGE_new.md
    python scripts/triage.py --write "$generated" "$@"
    if diff -u TRIAGE.md "$generated"; then
        echo "triage: 与 TRIAGE.md 一致。"
    else
        echo >&2
        echo "error: 变异检测结果与 TRIAGE.md 不一致（见上面的 diff）。" >&2
        echo "       套件捕获缺陷的能力变了；若是新增变异体导致的纯增量差异，" >&2
        echo "       在同一个变更里重新生成并提交 TRIAGE.md。" >&2
        return 1
    fi
}

task_audit() {
    # AGENTS.md 验证第 3 步。四条都应当无输出；grep 无匹配返回 1，所以这里判的
    # 是输出是否为空，而不是退出码。
    local failed=0
    check() {
        local label="$1" output="$2"
        if [ -n "$output" ]; then
            echo "FAIL  $label" >&2
            printf '%s\n' "$output" >&2
            failed=1
        else
            echo "ok    $label"
        fi
    }

    check "Page Object 穿透（tests/ 里的 _page.page.）" \
        "$(grep -rn '_page\.page\.' tests/ || true)"
    check "快照式断言（tests/ 里对 text_content/is_visible/all_text_contents 的 assert）" \
        "$(grep -rnE 'assert .*(text_content|is_visible|all_text_contents)\(\)' tests/ || true)"
    check "结构化选择器（pages/ 里的 locator(\"#）" \
        "$(grep -rn 'locator("#' pages/ || true)"
    # 末尾的 grep -v 过滤注释行：base_page.py 用一句
    # get_by_role("button", name="Add") 作为梯子说明的例子，那是散文不是定位器。
    check "硬编码文案（pages/ 里的 name=\"大写开头）" \
        "$(grep -rn 'name="[A-Z]' pages/ | grep -v ':[0-9]*: *#' || true)"

    return "$failed"
}

task_perf() {
    if ! command -v jmeter >/dev/null 2>&1; then
        cat >&2 <<'MSG'
error: 镜像里没有 jmeter。

性能测试需要 perf target 的镜像（多带一个 JDK 21 + JMeter）。用这两个 service
之一：

    docker compose run --rm perf        # 只跑压测
    docker compose run --rm all         # 四类检查一次跑完

详见 DOCKER.md。
MSG
        return 1
    fi
    # 显式用 bash 起，不依赖文件的执行位：Windows 上仓库放在 NTFS 盘再挂进来时，
    # 权限位可能已经在文件系统这一层丢掉了。
    bash perf/run_perf.sh "$@"
}

task_all() {
    # 刻意不 fail fast：一次跑完拿到完整的失败清单，比跑一半停下来有用得多。
    local -a failed=()
    local -a order=(pytest triage audit perf)
    local name
    for name in "${order[@]}"; do
        echo
        echo "=============================================================="
        echo "  $name"
        echo "=============================================================="
        if ! "task_${name}"; then
            failed+=("$name")
        fi
    done

    echo
    echo "=============================================================="
    if [ "${#failed[@]}" -gt 0 ]; then
        echo "  FAILED: ${failed[*]}"
        echo "=============================================================="
        return 1
    fi
    echo "  全部通过：${order[*]}"
    echo "=============================================================="
}

# --- 分发 ----------------------------------------------------------------

# DEFAULT_TASK 由镜像给出：test target 是 pytest，perf target 是 perf。
default_task="${DEFAULT_TASK:-pytest}"

run_task() {
    local name="$1"; shift
    case "$name" in
        pytest) task_pytest "$@" ;;
        triage) task_triage "$@" ;;
        audit)  task_audit "$@" ;;
        perf)   task_perf "$@" ;;
        all)    task_all "$@" ;;
        *)      echo "error: 未知任务 $name" >&2; return 2 ;;
    esac
}

if [ "$#" -eq 0 ]; then
    run_task "$default_task"
    exit $?
fi

case "$1" in
    pytest|triage|audit|perf|all)
        task="$1"; shift
        run_task "$task" "$@"
        ;;
    -*)
        # 以 - 开头的一定是参数，不可能是命令名（也不能拿去喂 command -v）。
        run_task "$default_task" "$@"
        ;;
    *)
        if command -v "$1" >/dev/null 2>&1; then
            exec "$@"
        else
            # 既不是任务名也不是可执行文件 —— 当成默认任务的参数，
            # 比如一个测试文件路径，或者一个 JMeter 场景名。
            run_task "$default_task" "$@"
        fi
        ;;
esac
