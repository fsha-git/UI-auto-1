# UI 自动化测试框架（Playwright + Pytest）

一个以本地静态 Demo 站点为被测对象的完整 UI 自动化框架：登录、待办列表、数据看板
（图表/表格）三个页面，配一个真实的 Python 后端，覆盖功能测试、Mock 测试、
国际化测试、变异测试（mutation testing）、代码覆盖率染色，以及基于 JMeter 的
六类负载/性能测试。演示账号：`demo` / `demo123`。

## 快速开始

```bash
cd /Users/shafelix/mywork2/UI_auto_1
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

跑一次全量测试确认环境搭好了：

```bash
pytest
```

## 项目结构

| 路径 | 说明 |
|---|---|
| `web/login.html` | 登录页 |
| `web/demo.html` | 主 Demo 页（待办列表 / 复选框 / 计数器），需登录后访问 |
| `web/dashboard.html` | 数据看板页（柱状图 + 表格 + 合计），需登录，拉取 `GET /api/stats` |
| `web/bugs/*.html` | `demo.html` 的 11 个冻结变异体，每个注入一个缺陷，用于变异测试 |
| `web/i18n/` | 前端读取的文案目录（`catalog.js`）与应用脚本（`apply.js`） |
| `server/app.py` | Demo 后端（静态文件 + `/api/*` JSON 接口：登录、看板数据、待办 CRUD） |
| `pages/base_page.py` | Page Object 公共基础设施（导航、session token、定位器策略） |
| `pages/i18n.py` | 测试端读取的文案目录解析器（对应 `web/i18n/catalog.js`） |
| `pages/login_page.py`、`pages/demo_page.py`、`pages/dashboard_page.py` | 三个页面的 Page Object |
| `tests/` | pytest 测试；`tests/test_api.py` 是纯 API 测试（不启动浏览器） |
| `scripts/triage.py` | 用 `tests/test_demo.py` 逐一跑 `web/bugs/*.html`，统计每个缺陷被哪些测试捕获 |
| `scripts/js_coverage.py` | 基于 CDP 的 V8 精确覆盖率采集器，生成前端内联 JS 的染色报告 |
| `perf/` | JMeter 负载/压力/阶梯/尖峰/长稳/并发测试计划、回归门禁、跨运行趋势看板 |
| `reports/` | 各类测试报告输出目录（已 gitignore，见下文） |

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
pytest tests/test_i18n.py           # 中英文两个 locale 的全量交互回归
```

用 `--demo-html` 把套件指向某个注入了缺陷的变异体，而不是默认的 `web/demo.html`：

```bash
pytest --demo-html web/bugs/bug_add_dedupes_items.html
```

调试单个失败用例：

```bash
playwright show-trace test-results/<用例目录>/trace.zip   # 逐帧看 DOM/网络/console
playwright show-report                                     # 打开 Playwright 自带报告
playwright codegen http://localhost:8000/demo.html         # 录制生成测试代码
```

## 测试报告

一次 `pytest` 运行会同时产出以下报告，全部在 `reports/` 下（已 gitignore）：

| 报告 | 路径 | 如何生成 |
|---|---|---|
| HTML 测试报告（含失败截图） | `reports/report.html` | `pytest --html=reports/report.html --self-contained-html` |
| Python 覆盖率（`server/` + `pages/`） | `reports/coverage-py/index.html` | 默认开启，见 `pytest.ini` 的 `addopts` |
| 前端 JS 染色（`web/*.html` 内联脚本） | `reports/coverage-js/index.html` | 每次 `pytest` 自动采集，详见 [`COVERAGE.md`](COVERAGE.md) |
| 变异测试报告 | [`TRIAGE.md`](TRIAGE.md) | `python scripts/triage.py --write TRIAGE.md` |
| 性能测试趋势看板 | `reports/jmeter/perf_dashboard.html` | `perf/run_perf.sh` 结束时自动生成，详见 [`PERFORMANCE.md`](PERFORMANCE.md) |

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

- **`scripts/triage.py`** — 变异测试的核心：对 `web/bugs/` 下每一个变异体跑一遍
  `tests/test_demo.py`，记录哪些用例捕获了哪个缺陷。改动共享标记（Page Object /
  定位器 / 文案）后必须重新生成并 diff：

  ```bash
  python scripts/triage.py --write /tmp/TRIAGE_new.md
  diff TRIAGE.md /tmp/TRIAGE_new.md   # 非空 diff 意味着测试的缺陷检出能力被削弱了
  ```

- **`scripts/js_coverage.py`** — 前端 JS 染色采集器，由 `tests/conftest.py` 的
  `js_coverage` fixture 在每个 UI 测试里自动调用，无需手动运行。

- **`perf/run_perf.sh`** — 一键运行 JMeter 负载/性能测试：

  ```bash
  perf/run_perf.sh all            # performance / stress / stepload / spike / concurrency
  perf/run_perf.sh performance    # 只跑基线性能
  perf/run_perf.sh soak           # 长稳测试（默认 30 分钟，不含在 all 里）
  ```

  详见 [`PERFORMANCE.md`](PERFORMANCE.md)，含账号隔离、六类场景说明、回归门禁、
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

## 相关文档

| 文档 | 内容 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | 面向改动者的强制规范：定位器、断言、变异测试不可回归、压测账号隔离等六条约定，以及提交前必须跑的验证清单 |
| [`LOCATORS.md`](LOCATORS.md) | 定位器优先级策略详解，及其与文案目录的关系 |
| [`COVERAGE.md`](COVERAGE.md) | API 测试清单、Python 覆盖率与前端 JS 染色两条流水线的原理 |
| [`MOCK_TESTS.md`](MOCK_TESTS.md) | `tests/test_dashboard.py` 逐个 Mock 测试场景说明 |
| [`PERFORMANCE.md`](PERFORMANCE.md) | JMeter 六类场景、账号隔离、回归门禁、趋势看板、结果有效性边界 |
| [`TRIAGE.md`](TRIAGE.md) | `scripts/triage.py` 生成的变异测试检出报告 |
