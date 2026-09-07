#!/usr/bin/env bash
# 容器里的任务分发器。第一个参数是任务名；其余参数透传给该任务底下的命令。
#
#   pytest [pytest 参数...]   全量 pytest 套件
#   triage                    30 个变异体的检测能力回归，等价于 AGENTS.md 验证第 2 步
#   audit                     AGENTS.md 验证第 3 步的四条约定 grep
#   coverage                  增量代码染色门禁：改动行 100% 覆盖（读上一次 pytest 的报告）
#   perf   [场景 | -J 参数...] JMeter 压测，等价于 perf/run_perf.sh（需要 perf 镜像）
#   all                       pytest/triage/audit/perf 依次跑完，不中途退出，最后汇总
#
# coverage 刻意不在 all 里：它要有一个 base 分支才有意义（$COVERAGE_BASE，默认
# origin/main），那是 PR 的语境；all 是本机的全量自检，没有"相对谁的增量"这回事。
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
    # eval 期间必须关掉 glob（set -f）：否则 `-k test_*` 里的 test_* 会被当前
    # 目录的文件名展开，参数被悄悄改写成一串路径。事后无条件恢复。
    local -a extra=()
    if [ -n "${PYTEST_ARGS:-}" ]; then
        set -f
        eval "extra=(${PYTEST_ARGS})"
        set +f
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

task_coverage() {
    # PR 增量代码染色门禁：只看 git diff 出来的改动行，要求 100% 被测试染色。
    #
    # 分母天然是收窄的——Python 侧 XML 只含 server/ 与 pages/（pytest.ini 的 --cov
    # 口径），JS 侧 XML 只含 web/*.html——所以只动文档、CI 或 tests/ 的变更分母为空，
    # diff-cover 直接判通过。这里不需要再叠一层 include/exclude 规则。
    local base="${COVERAGE_BASE:-origin/main}"
    local py_xml=reports/coverage-py/coverage.xml
    local js_xml=reports/coverage-js/coverage.xml

    if [ ! -f "$py_xml" ]; then
        cat >&2 <<MSG
error: 找不到 $py_xml。

增量门禁读的是上一次 pytest 留下的覆盖报告，它不替你跑测试——一个任务只做一件事，
CI 上也不该把整套用例跑两遍。先跑：

    docker compose run --rm tests

再跑这个任务。
MSG
        return 1
    fi

    # 绑定挂载的属主是宿主机上的你，容器却以另一个 UID 在跑（compose 的 user:），
    # git 会判成 dubious ownership 直接罢工。镜像里 HOME=/tmp 是可写的，这条全局
    # 配置落在 /tmp/.gitconfig，随容器一起消失，不碰宿主机的 .gitconfig。
    git config --global --add safe.directory /work

    if ! git rev-parse --verify --quiet "${base}^{commit}" >/dev/null; then
        cat >&2 <<MSG
error: 找不到用来比对的 base 引用 ${base}。

CI 上 checkout 要用 fetch-depth: 0，并在 PR 事件下显式 fetch 一次 base 分支的远端
引用；本机上先 \`git fetch origin\`，或者用 COVERAGE_BASE 指一个确实存在的引用：

    COVERAGE_BASE=origin/main docker compose run --rm tests coverage
MSG
        return 1
    fi

    mkdir -p reports/diff-cover

    local failed=0
    echo "增量覆盖（Python，阻塞）：改动行对比 ${base}，要求 100%"
    if ! diff-cover "$py_xml" \
        --compare-branch "$base" \
        --fail-under 100 \
        --format "html:reports/diff-cover/python.html,markdown:reports/diff-cover/python.md"; then
        failed=1
    fi

    # 前端 JS 侧只报告、不阻塞：CDP 会话在新页面开始加载之后才附着，守卫脚本那类
    # 顶层语句会被染成"红色但其实执行过"（COVERAGE.md 三）。现在就卡死等于误杀。
    # 先把数字摆到 PR 上，攒几轮确认没有假红再决定要不要改成阻塞。
    if [ -f "$js_xml" ]; then
        echo
        echo "增量覆盖（前端 JS，仅供参考，不影响退出码）："
        diff-cover "$js_xml" \
            --compare-branch "$base" \
            --fail-under 0 \
            --format "html:reports/diff-cover/js.html,markdown:reports/diff-cover/js.md" || true
    fi

    if [ "$failed" -ne 0 ]; then
        echo >&2
        echo "error: 有改动行没有被测试染色（清单见上，逐行报告在 reports/diff-cover/python.html）。" >&2
        echo "       补测试把它跑绿，或者在 PR 上走人工豁免审批——见 COVERAGE.md 六。" >&2
    fi
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
        coverage) task_coverage "$@" ;;
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
    pytest|triage|audit|coverage|perf|all)
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
