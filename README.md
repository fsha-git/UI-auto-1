# UI 自动化测试框架（Playwright + Pytest）

一个以本地静态 Demo 站点为被测对象的完整 UI 自动化框架：登录、待办列表、数据看板
（图表/表格）、Canvas 多序列折线趋势图（悬停 tooltip + 图例开关 + 数据重生成）、
个人资料（新标签页打开）与快速便签弹窗（`window.open`）多个页面，
配一个真实的 Python 后端，覆盖功能测试、Mock 测试、多窗口/弹窗测试、国际化测试、
变异测试（mutation testing）、代码覆盖率染色，以及基于 JMeter 的
七类负载/性能测试。另有一个**低代码可视化测试页面**：按 BDD 结构和时序编排 Mock
业务场景、一键跑真实 pytest、回放 Playwright trace（见 [`STUDIO.md`](STUDIO.md)）。
演示账号：`demo` / `demo123`。

## 快速开始

### 用 Docker 跑（macOS / Linux / Windows 通用）

宿主机只需要 Docker，不用装 Python、Playwright、浏览器、JDK 或 JMeter。命令在三个
平台上逐字相同：

```bash
docker compose run --rm all
```

一次跑完 pytest 全量套件 → 变异检测回归 → 约定审计 → JMeter 压测。只想跑 pytest：

```bash
docker compose run --rm tests
```

报告仍然落在宿主机的 `reports/` 与 `test-results/`。分服务命令、传参写法、Linux 的
文件属主处理、以及已知取舍见 [`DOCKER.md`](DOCKER.md)。

### 装在本机跑

```bash
git clone <本仓库地址> && cd UI_auto_1   # 已有本地副本可直接 cd 进仓库根目录
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

`requirements.txt` 锁死了直接依赖的版本，其中 `playwright==1.62.0` 必须与
`docker/Dockerfile` 的基础镜像 tag 一致（原因见 [`DOCKER.md`](DOCKER.md)）。

跑一次全量测试确认环境搭好了：

```bash
pytest
```

## 项目结构

| 路径 | 说明 |
|---|---|
| `web/login.html` | 登录页 |
| `web/demo.html` | 主 Demo 页（待办列表 / 复选框 / 计数器 / Canvas 多序列折线趋势图），需登录后访问 |
| `web/dashboard.html` | 数据看板页（柱状图 + 表格 + 合计），需登录，拉取 `GET /api/stats` |
| `web/profile.html` | 个人资料页（用户名 + 实时待办数），从 `demo.html` 以新标签页（`target=_blank`）打开，拉取 `GET /api/profile` |
| `web/popup.html` | 快速便签弹窗，由 `demo.html` 的按钮 `window.open()` 打开，`postMessage` 回传后自关闭 |
| `web/studio.html` | 低代码可视化测试页面：BDD 步骤面板 + 时序画布 + Gherkin 预览 + 一键运行 + trace 回放，详见 [`STUDIO.md`](STUDIO.md) |
| `web/studio/steps.js` | Studio 步骤库（唯一真源，严格 JSON；被页面、Page Object、BDD 步骤定义、后端渲染器共读） |
| `web/bugs/*.html` | 30 个冻结变异体（`bug_*`），每个注入一个缺陷，用于变异测试：11 个经典 demo 变异体 + 4 个多窗口变异体（`bug_win_*`，其中两个通过 `win_*` 伴生页面注入缺陷）+ 6 个趋势图变异体（`bug_chart_*`，只保留趋势图 section 的精简副本）+ 9 个 Studio 变异体（`bug_studio_*`，`studio.html` 的副本） |
| `web/i18n/` | 前端读取的文案目录（`catalog.js`）与应用脚本（`apply.js`） |
| `server/app.py` | Demo 后端（静态文件 + `/api/*` JSON 接口：登录、看板数据、待办 CRUD） |
| `studio/` | Studio 后端（工装，不属被测应用）：场景校验与 Gherkin 渲染、起 pytest、收 trace/报告，`python -m studio` 启动 |
| `pages/base_page.py` | Page Object 公共基础设施（导航、session token、定位器策略） |
| `pages/i18n.py` | 测试端读取的文案目录解析器（对应 `web/i18n/catalog.js`） |
| `pages/studio_steps.py` | 测试端读取的 Studio 步骤库解析器（对应 `web/studio/steps.js`，写法与 `pages/i18n.py` 一致） |
| `pages/login_page.py`、`pages/demo_page.py`、`pages/dashboard_page.py`、`pages/profile_page.py`、`pages/popup_page.py`、`pages/studio_page.py` | 各页面的 Page Object；多窗口管道（`expect_page` / `expect_popup`）封装在 `DemoPage` 里 |
| `tests/` | pytest 测试；`tests/test_api.py` 是纯 API 测试（不启动浏览器），`tests/test_windows.py` 是多标签页/弹窗测试，`tests/test_chart.py` 是趋势图测试，`tests/test_studio.py` 是 Studio 页面测试，`tests/test_studio_backend.py` 是 Studio 后端的无浏览器测试 |
| `tests/test_dashboard_bdd.py` | pytest-bdd 步骤定义：Studio 编排出的场景的唯一执行实现，每一步都走 `DashboardPage` |
| `tests/features/` | 已提交的 Gherkin 场景，也是 Studio"保存为 feature"的落点；日常 `pytest` 会跑到 |
| `scripts/triage.py` | 对 `web/bugs/bug_*.html` 逐一跑对应的测试文件（经典变异体跑 `test_demo.py`，`bug_win_*` 跑 `test_windows.py`，`bug_chart_*` 跑 `test_chart.py`，`bug_studio_*` 跑 `test_studio.py`），统计每个缺陷被哪些测试捕获 |
| `scripts/js_coverage.py` | 基于 CDP 的 V8 精确覆盖率采集器，生成前端内联 JS 的染色报告（HTML + 给门禁读的 Cobertura XML） |
| `perf/` | JMeter 七类测试计划（负载/压力/阶梯/尖峰/长稳/并发/个人资料只读）、回归门禁、跨运行趋势看板 |
| `reports/` | 各类测试报告输出目录（已 gitignore，见下文） |
| `docker/Dockerfile` | 两个 build target：`test`（Python + Chromium）与 `perf`（在它之上再加 JDK 21 + JMeter） |
| `docker/entrypoint.sh` | 容器内的任务分发器：`pytest` / `triage` / `audit` / `coverage` / `perf` / `all` |
| `docker-compose.yml` | 四个 service（`tests` / `triage` / `perf` / `all`），三平台通用的一键入口 |
| `.github/workflows/tests.yml` | CI：跑与本地逐字相同的 compose 命令，上传报告 artifact；PR 上多一道增量代码染色门禁（`coverage-gate`），见 [`COVERAGE.md`](COVERAGE.md) 第六节 |
| `.coveragerc` | coverage.py 的两条配置：`relative_files` 让报告路径相对仓库根，`concurrency = greenlet,thread` 让追踪器跟得上 Playwright 同步 API 的 greenlet 切换——两条都是为了门禁在宿主机和容器里判出同一个结果 |

## 运行测试

```bash
pytest                              # 全量测试（默认对象：web/demo.html）
pytest --headed                     # 有头模式，观察浏览器实际交互
pytest tests/test_demo.py           # 只跑某个测试文件
pytest -k "checkbox"                # 按用例名关键字过滤
pytest -m "not perf"                # 跳过前端渲染性能护栏（迭代时更快）
pytest tests/test_frontend_perf.py -v   # 只跑前端渲染性能护栏
```

只跑某一类测试：

```bash
pytest tests/test_api.py            # 纯 API 测试，不启动浏览器
pytest tests/test_dashboard.py -v   # 数据看板的 Mock 测试（见 MOCK_TESTS.md）
pytest tests/test_windows.py        # 多标签页 / window.open 弹窗 / 跨窗口交互
pytest tests/test_chart.py          # Canvas 趋势图：多序列渲染 / 悬停 tooltip / 图例开关 / 数据重生成
pytest tests/test_i18n.py           # 中英文两个 locale 的全量交互回归
pytest tests/test_studio.py         # 低代码 Studio 页面（runner 接口用 page.route() mock 掉）
pytest tests/test_studio_backend.py # Studio 后端：步骤库 / Gherkin 渲染 / 校验 / HTTP 接口
pytest tests/test_dashboard_bdd.py  # tests/features/ 下的 Gherkin 场景
```

PR 的增量代码染色门禁（改动行 100% 覆盖，未达标要人工审批才能合并，
详见 [`COVERAGE.md`](COVERAGE.md) 第六节）：

```bash
docker compose run --rm tests            # 先跑测试，产出两份覆盖报告
docker compose run --rm tests coverage   # 再判改动行的覆盖率

# 不用 Docker 的等价写法（只判 Python 侧）：
diff-cover reports/coverage-py/coverage.xml --compare-branch origin/main --fail-under 100
```

启动低代码可视化测试页面（详见 [`STUDIO.md`](STUDIO.md)）：

```bash
python -m studio --port 8100
# 浏览器打开 http://127.0.0.1:8100/studio.html（先用 demo / demo123 登录）
```

用 `--demo-html` 把套件指向某个注入了缺陷的变异体，而不是默认的 `web/demo.html`：

```bash
pytest --demo-html web/bugs/bug_add_dedupes_items.html
```

调试单个失败用例：

```bash
playwright show-trace test-results/<用例目录>/trace.zip   # 逐帧看 DOM/网络/console

# codegen 需要先手动起一个服务监听该端口（pytest 自己的 demo_server fixture
# 用的是随机端口，起不来给 codegen 用）：
python -m server --port 8000
playwright codegen http://localhost:8000/demo.html         # 录制生成测试代码
```

## 测试报告

**每次 `pytest` 运行自动产出**（无需额外参数，`reports/` 已 gitignore）：

| 报告 | 路径 | 说明 |
|---|---|---|
| Python 覆盖率（`server/` + `pages/`） | `reports/coverage-py/index.html` | 默认开启，见 `pytest.ini` 的 `addopts` |
| 前端 JS 染色（`web/*.html` 内联脚本） | `reports/coverage-js/index.html` | 每次 `pytest` 自动采集，详见 [`COVERAGE.md`](COVERAGE.md) |
| 上面两份的机器可读版（Cobertura） | `reports/coverage-py/coverage.xml`、`reports/coverage-js/coverage.xml` | 增量染色门禁读它们算改动行的覆盖率 |

**需要显式加参数 / 单独运行脚本才会产出**：

| 报告 | 路径 | 如何生成 |
|---|---|---|
| HTML 测试报告（含失败截图） | `reports/report.html` | `pytest --html=reports/report.html --self-contained-html` |
| 变异测试报告 | [`TRIAGE.md`](TRIAGE.md)（仓库根目录，不在 `reports/` 下） | `python scripts/triage.py --write TRIAGE.md` |
| 增量染色门禁报告 | `reports/diff-cover/python.html`、`js.html` | `docker compose run --rm tests coverage` |
| 性能测试趋势看板 | `reports/jmeter/perf_dashboard.html` | 单独跑 `perf/run_perf.sh`（JMeter 场景，不随 `pytest` 触发）结束时自动生成，详见 [`PERFORMANCE.md`](PERFORMANCE.md) |

生成带截图的完整 HTML 报告：

```bash
pytest --html=reports/report.html --self-contained-html
```

`--demo-html` 和 `--html` 可以组合使用，用于导出某个变异体触发失败时的报告：

```bash
pytest --demo-html web/bugs/bug_add_dedupes_items.html \
       --html=reports/report.html --self-contained-html
```

`reports/coverage-py/index.html` 和 `reports/coverage-js/index.html` 是逐行染色
的源码视图（绿色 = 执行过，红色 = 从未执行），可直接用浏览器打开
（`file://` 即可）。

## 核心脚本

- **`scripts/triage.py`** — 变异测试的核心：对 `web/bugs/` 下每一个 `bug_*`
  变异体跑一遍对应的测试文件（按文件名前缀选择：经典变异体 →
  `tests/test_demo.py`，`bug_win_*` → `tests/test_windows.py`，`bug_chart_*`
  → `tests/test_chart.py`，`bug_studio_*` → `tests/test_studio.py`），记录哪些用例捕获了哪个缺陷。改动共享标记（Page Object / 定位器 / 文案）后必须重新生成并
  diff：

  ```bash
  python scripts/triage.py --write /tmp/TRIAGE_new.md
  diff TRIAGE.md /tmp/TRIAGE_new.md   # 非空 diff 意味着测试的缺陷检出能力被削弱了
  ```

- **`scripts/js_coverage.py`** — 前端 JS 染色采集器，由 `tests/conftest.py` 的
  `js_coverage` fixture 在每个 UI 测试里自动调用，无需手动运行。

- **`perf/run_perf.sh`** — 一键运行 JMeter 负载/性能测试：

  ```bash
  perf/run_perf.sh all            # performance / stress / stepload / spike / concurrency / profile
  perf/run_perf.sh performance    # 只跑基线性能
  perf/run_perf.sh profile        # 只跑 /api/profile 只读场景
  perf/run_perf.sh soak           # 长稳测试（默认 30 分钟，不含在 all 里）
  ```

  详见 [`PERFORMANCE.md`](PERFORMANCE.md)，含账号隔离、七类场景说明、回归门禁、
  趋势看板用法。

## 设计要点（速览）

以下几点是理解这套框架时最容易踩坑的地方，完整说明见各自的文档：

- **定位器优先级**：role + 可访问名称 优先，逐级降级到 test id / CSS。
  详见 [`LOCATORS.md`](LOCATORS.md)。
- **断言只用 `expect()`**：所有断言走 Playwright 的 web-first `expect()`（会
  重试），禁止对 `text_content()` / `is_visible()` 等一次性快照结果做断言。
- **登录一次，全程复用**：会话级 fixture 登录一次并保存 `storage_state` 到
  `.auth/state.json`，普通测试直接复用；需要跑登录流程本身的测试用
  `fresh_page` / `login_page`。
- **看板数据用 `page.route()` 做网络 Mock**：`dashboard.html` 默认由本地服务
  器返回固定数据，Mock 测试在导航前拦截 `/api/stats` 来构造空数据、报错、加
  载中等场景，详见 [`MOCK_TESTS.md`](MOCK_TESTS.md)。
- **压测账号与功能测试账号严格隔离**：功能测试用 `demo` 账号，压测用
  `perf/accounts.csv` 里独立的 50 个账号，后端按账号分区存储，详见
  [`PERFORMANCE.md`](PERFORMANCE.md)。
- **低代码编排没有第二套执行引擎**：Studio 把时序画布渲染成真正的 `.feature`，
  交给 `pytest` + `pytest-bdd` 跑，用的是同一批 fixture 和同一批 Page Object，
  详见 [`STUDIO.md`](STUDIO.md)。

## 相关文档

| 文档 | 内容 |
|---|---|
| [`DOCKER.md`](DOCKER.md) | 容器化测试环境：四个 service、传参、报告落点、Linux 文件属主、CI、镜像版本约束 |
| [`AGENTS.md`](AGENTS.md) | 面向改动者的强制规范：定位器、断言、变异测试不可回归、压测账号隔离、文档同步等七条约定，以及提交前必须跑的验证清单 |
| [`LOCATORS.md`](LOCATORS.md) | 定位器优先级策略详解，及其与文案目录的关系 |
| [`COVERAGE.md`](COVERAGE.md) | API 测试清单、Python 覆盖率与前端 JS 染色两条流水线的原理 |
| [`MOCK_TESTS.md`](MOCK_TESTS.md) | `tests/test_dashboard.py` 逐个 Mock 测试场景说明 |
| [`STUDIO.md`](STUDIO.md) | 低代码可视化测试页面：BDD 步骤库、时序编排、一键运行、trace 回放、安全边界 |
| [`PERFORMANCE.md`](PERFORMANCE.md) | JMeter 七类场景、账号隔离、回归门禁、趋势看板、结果有效性边界 |
| [`TRIAGE.md`](TRIAGE.md) | `scripts/triage.py` 生成的变异测试检出报告 |
