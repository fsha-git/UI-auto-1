# 低代码可视化测试页面（Mock 场景 Studio）

`web/studio.html` 是一个**低代码测试编排页面**：把 [`MOCK_TESTS.md`](MOCK_TESTS.md)
里那 11 个 `page.route()` Mock 场景所用到的全部手法，拆成一个固定的步骤库，让人在
浏览器里按 **BDD 结构（Given / When / Then）** 和**时序**拼出业务场景，一键真正跑一次
pytest，看到每一步的成败与耗时，并直接打开这次运行的 Playwright trace。

编排结果可以保存成 `tests/features/*.feature`，进入日常 `pytest` 全量回归——低代码
产出的不是一次性的点击记录，而是可提交的测试资产。

```bash
.venv/bin/python -m studio --port 8100
# 浏览器打开 http://127.0.0.1:8100/studio.html
# 首次访问会被 auth gate 弹到 login.html，用 demo / demo123 登录
```

---

## 1. 它为什么长这样

三条设计约束决定了全部结构：

1. **没有第二套执行引擎。** 场景不是被页面"解释执行"的，而是被渲染成一个真正的
   Gherkin `.feature` 文件，交给 `pytest` + `pytest-bdd` 跑
   （`tests/test_dashboard_bdd.py`）。用的是仓库自己的 fixture
   （`demo_server` / `storage_state` / `page`）、自己的 Page Object
   （`pages/dashboard_page.py`）、自己的断言规范（web-first `expect()`）。
   低代码路径和手写测试跑的是同一条链路，不存在"页面上绿了、`pytest` 里红了"。
2. **步骤库只有一份定义。** `web/studio/steps.js` 是唯一真源，被四方读取：页面的步骤
   面板与 Gherkin 预览、`pages/studio_steps.py`（Page Object）、
   `tests/test_dashboard_bdd.py` 的步骤定义（`parsers.parse` 的模板直接取自它）、
   以及 `studio/runner.py` 的 feature 渲染器。这是照抄
   [`web/i18n/catalog.js`](web/i18n/catalog.js) 的既有做法，理由也一样：一句 Gherkin
   改了名，四处不可能对不上。
3. **不碰 `server/app.py`。** 被测应用的接口面就是 JMeter 压测的基线
   （见 [`AGENTS.md`](AGENTS.md) §6：新接口要配新场景）。Studio 的 `/studio/api/*`
   是工装接口、永远不进压测，所以它挂在 `StudioHandler(DemoApiHandler)` 子类上，
   `server/app.py` 一行未动。

```
浏览器 web/studio.html
  │  步骤面板 ← web/studio/steps.js（window.STUDIO_STEPS，严格 JSON，<script> 直接加载）
  │  时序画布 → 场景 JSON
  ▼  POST /studio/api/run
studio/（独立进程，默认只绑 127.0.0.1）
  │  1. 按步骤库校验场景 JSON（步骤 id、参数类型）
  │  2. 渲染成 reports/studio/runs/<run_id>/scenario.feature
  │  3. subprocess 起 pytest：STUDIO_FEATURE=<该 feature>
  │       tests/test_dashboard_bdd.py --tracing=on --output <run>/artifacts
  │       --report-log <run>/report.jsonl --html <run>/report.html
  │       --reruns 0 --no-cov -p studio.bdd_report_plugin
  ▼  4. 汇总用例结果 / 每步状态 / trace.zip 路径 / 执行命令 / pytest stdout
pytest（真实套件，复用现有 conftest 的全部 fixture）
```

---

## 2. 页面

### 编排场景（Compose scenario）

| 区域 | 说明 |
|---|---|
| 步骤面板 | 按 `Given` / `When` / `Then` 分三组，每项显示这一步的 Gherkin 句子和它的参数输入框，点"加入时序"push 到画布 |
| 时序画布 | 有序的步骤卡片。左侧是序号，中间三条泳道（`mock` / `browser` / `assert`）标出这一步由谁执行——自上而下读就是一张时序图。每张卡带 上移 / 下移 / 删除 |
| Gherkin 预览 | 参数替换后的 `.feature` 全文，随每一次编辑实时更新，和后端写出去的字节一致 |
| 运行结果 | **独立面板，在两个标签页之外、始终可见**：每步状态灯（`passed` / `failed` / `skipped` / `pending`）+ 耗时、逐用例结果行、失败信息、**执行的 pytest 命令**、**pytest 原始输出**、trace 命令、HTML 报告链接 |

**时序不是装饰。** "加载中"这个场景的全部语义就在顺序里：

```
Given the /api/stats endpoint is held pending     ← 先挂起，不放行
When  I open the dashboard                        ← 再导航
Then  the loading indicator is visible            ← 此刻才观察得到加载态
When  I release the pending /api/stats request …  ← 然后才放行
Then  the chart bars are "7"
```

把"挂起"挪到导航后面，或者把"放行"挪到断言前面，这个场景就什么都测不到了——所以
画布从不对步骤做任何排序或分组，用户摆成什么样就是什么样。

### 现有 Mock 用例（Existing mock tests）

列出 `tests/test_dashboard.py` 的用例，勾选后一键运行，同样出 trace 和 HTML 报告。
这份清单是启动时用 `pytest --collect-only` 问 pytest 自己要的，不是 `MOCK_TESTS.md`
的副本——有人往那个文件里加第 12 个场景，Studio 自动就有。

**这个模式没有时序画布可点亮，所以证据全靠三块面板**：逐用例结果行（每行一个
node id + 通过/失败 + 耗时）、**执行的 pytest 命令**（含 `STUDIO_FEATURE=…`
之类的环境前缀，可直接粘进终端复现）、以及 **pytest 的原始输出**（跑的是 `-v`，
每个用例一行）。没有这三块，页面只会显示一行 `passed in 2.03s`，用户无从判断到底
跑没跑。这三块面板在编排模式下同样渲染。

**运行结果面板刻意放在两个标签页之外**——它一度写在编排面板里，而这个标签页恰好会把
编排面板 `display:none`，于是从这里发起的运行把全部证据渲染进了一个隐藏容器，用户
什么都看不到。`tests/test_studio.py` 现在用 `to_be_visible()` 而不只是"元素存在"来
断言这几块，`bug_studio_result_hidden_on_suite_tab` 冻结了这个缺陷。

pytest 的输出会先剥掉 ANSI 颜色转义（跑的时候带 `--color=no`，`_ANSI` 正则兜底
`PY_COLORS` / `FORCE_COLOR` 之类的环境覆盖）——它要进的是 `<pre>`，不是终端。
命令在 `subprocess` 启动之前就发布，所以运行还没结束时页面上就能看到"正在等什么"；
输出按最后 400 行 / 40000 字符截断（`MAX_OUTPUT_LINES` / `MAX_OUTPUT_CHARS`），
截断时开头标 `[... earlier output trimmed ...]`——它要回答的是"到底跑没跑"，
不是把每次状态轮询变成一兆 JSON。

---

## 3. 步骤库

`web/studio/steps.js` 每条：`{keyword, lane, template, params}`。`template` 用
pytest-bdd 的 `parsers.parse` 语法（`{name}` 字符串、`{name:d}` 整数）。
`Given` / `When` / `Then` 是 Gherkin 语法而不是 UI 文案，所以**故意不进**
`web/i18n/catalog.js`。

| id | keyword | lane | Gherkin |
|---|---|---|---|
| `g_no_mock` | Given | mock | the /api/stats endpoint is not mocked |
| `g_mock_data` | Given | mock | the /api/stats endpoint returns labels "{labels}" and values "{values}" |
| `g_mock_empty` | Given | mock | the /api/stats endpoint returns no data |
| `g_mock_status` | Given | mock | the /api/stats endpoint returns HTTP status {status:d} |
| `g_mock_aborted` | Given | mock | the /api/stats endpoint aborts the connection |
| `g_mock_malformed` | Given | mock | the /api/stats endpoint returns the malformed body "{body}" |
| `g_mock_pending` | Given | mock | the /api/stats endpoint is held pending |
| `g_mock_sequence` | Given | mock | the /api/stats endpoint returns the dataset sequence "{datasets}" |
| `w_open_dashboard` | When | browser | I open the dashboard |
| `w_click_refresh` | When | browser | I click the Refresh button |
| `w_release_pending` | When | browser | I release the pending /api/stats request with labels "{labels}" and values "{values}" |
| `w_wait_loaded` | When | browser | I wait for the dashboard to finish loading |
| `t_bars` | Then | assert | the chart bars are "{values}" |
| `t_no_bars` | Then | assert | the chart renders no bars |
| `t_total` | Then | assert | the total is {total:d} |
| `t_rows` | Then | assert | the table has {count:d} rows |
| `t_empty_visible` | Then | assert | the empty-data message is visible |
| `t_empty_hidden` | Then | assert | the empty-data message is hidden |
| `t_error_visible` | Then | assert | an error message is shown |
| `t_error_contains` | Then | assert | the error message contains "{text}" |
| `t_loading_visible` | Then | assert | the loading indicator is visible |

`{datasets}` 的写法是 `A=1 | A,B=1,2 | A,B,C=1,2,3`：竖线分隔的多份数据集，
第 N 次请求拿第 N 份（对应
`test_dashboard_refresh_cycles_through_three_mock_datasets`）。

**"空数据"为什么单独一个步骤**：`parse` 的 `{name}` 占位符匹配不了空字符串，
`labels=""` 会直接变成"步骤未定义"；何况在面板上留一个"必须填空"的输入框也是糟糕的
交互。所以 `g_mock_empty` / `t_no_bars` 是显式的独立步骤。

### 加一个步骤

1. 往 `web/studio/steps.js` 里加一条（严格 JSON：不许注释、尾逗号、单引号）。
2. 在 `tests/test_dashboard_bdd.py` 里用 `@bdd_step("新 id")` 实现它，只允许调用
   `DashboardPage` 的方法和 `page.route()`。
3. 跑 `pytest tests/test_studio_backend.py`——那里的 parity 测试会断言
   "步骤库里每个 id 都有实现、反之亦然"，漏一边就红。

---

## 4. Trace 与报告

Studio 的每次运行都强制 `--tracing=on --screenshot=on --video=on`
（`pytest.ini` 日常是 `retain-on-failure`，因为全量跑不需要为通过的用例留 trace；
但 Studio 的承诺就是"刚才发生了什么，有录像"）。产物落在：

```
reports/studio/runs/<run_id>/
├── scenario.feature      # 这次跑的 Gherkin（编排模式）
├── report.jsonl          # pytest --report-log，用来还原用例结果
├── steps.jsonl           # 每一步的 outcome / 耗时（studio/bdd_report_plugin.py 写）
├── report.html           # self-contained HTML 报告，页面上有链接（新标签页直接渲染）
└── artifacts/<用例目录>/trace.zip
```

页面上给出可直接复制的命令，"打开 Trace"按钮则让后端在本机拉起 viewer：

```bash
playwright show-trace reports/studio/runs/<run_id>/artifacts/<用例目录>/trace.zip
```

`reports/` 已在 `.gitignore` 里，运行产物不会进版本库。

### 每步状态灯是怎么来的

pytest 自己的报告事件是**按用例**的，时序画布需要**按步骤**。
`studio/bdd_report_plugin.py` 挂 pytest-bdd 的 `pytest_bdd_after_step` /
`pytest_bdd_step_error` 钩子，把每一步写成一行 JSON。它只在 Studio 运行时用 `-p`
挂载，**不放进 `tests/conftest.py`**——日常 `pytest` 的行为和 Studio 出现之前
一模一样。日志按执行顺序写，而执行顺序就是时序顺序，所以结果能一一映射回卡片；
失败之后没跑到的步骤在页面上显示为 `skipped` 而不是绿色。

---

## 5. 保存成 feature

"保存为 feature"把当前场景写成 `tests/features/<slug>.feature`。
`tests/test_dashboard_bdd.py` 默认绑定整个 `tests/features/` 目录，所以保存下来的
场景立刻成为日常 `pytest` 的一部分：

```bash
.venv/bin/python -m pytest tests/test_dashboard_bdd.py -v
```

一次性运行则不写进这个目录——Studio 把 feature 写在 `reports/studio/runs/<run_id>/`
下，通过 `STUDIO_FEATURE` 环境变量指给那次 pytest。用环境变量而不是 pytest 选项，
是因为 `scenarios()` 在**模块 import 期**就要绑定，那时候还读不到 pytest 的选项。

仓库里已提交的示例场景在 `tests/features/dashboard_mock.feature`：加载态时序、
连续刷新换数据集、500 错误、空数据。

---

## 6. 安全边界

这个进程会**执行 pytest**，所以：

- `python -m studio` 默认只绑 `127.0.0.1`；要绑别的地址必须显式加 `--i-know`。
- 场景 JSON 的每个步骤 id 必须命中步骤库，每个参数名必须是该步骤声明过的，整数参数
  必须真的能转成整数（`pages/studio_steps.render_step` 负责，也正是写 feature 的
  那个函数）。
- `mode: "tests"` 的 node id 必须在 `pytest --collect-only` 收集到的清单里。
- 用户输入只以 **Gherkin 参数**的身份进入 feature 文件，从不拼进命令行：
  `subprocess` 一律传参数列表，从不用 `shell=True`。
- 产物下载端点用 `studio/runner.resolve_artifact()` 校验解析后的路径仍在该次运行的
  目录内，URL 里的 `..` 走不出去。

这些都在 `tests/test_studio_backend.py` 里有对应用例。

---

## 7. 它自己也是被测对象

按 [`AGENTS.md`](AGENTS.md) §1，Studio 页面自身带测试和冻结变异体：

| 文件 | 作用 |
|---|---|
| `pages/studio_page.py` | Studio 的 Page Object |
| `tests/test_studio.py` | Studio 的 UI 测试，**用 `page.route()` mock 掉 `/studio/api/*`**——既快又不会递归调起 pytest，顺带让 Studio 的测试和它服务的对象用同一套手法 |
| `tests/test_studio_backend.py` | 无浏览器测试：步骤库/渲染器/校验/路径守卫/HTTP 接口 |
| `web/bugs/bug_studio_*.html` | 9 个冻结变异体，由 `scripts/triage.py` 跑 `tests/test_studio.py` 逐一验证检出 |

| 变异体 | 注入的缺陷 |
|---|---|
| `bug_studio_step_order_ignored` | 上移/下移是空操作，场景顺序永远是加入顺序 |
| `bug_studio_remove_step_noop` | 删除步骤按钮不删 |
| `bug_studio_gherkin_drops_params` | 直出模板，参数一律不替换 |
| `bug_studio_run_sends_stale_scenario` | 运行提交的是上一次"加入步骤"时的快照，move/remove 不算数 |
| `bug_studio_step_result_always_passed` | 跑完之后每一步都画成绿色，无视真实 outcome |
| `bug_studio_run_evidence_hidden` | 执行命令与 pytest 输出永远不显示 |
| `bug_studio_test_results_missing` | 逐用例结果行永远不渲染 |
| `bug_studio_stale_output_kept` | 上一次运行的输出留在页面上并与本次叠加 |
| `bug_studio_result_hidden_on_suite_tab` | 运行结果面板跟着编排面板一起被隐藏，切到"现有 Mock 用例"跑完什么都看不见 |

---

## 8. 相关文件

| 路径 | 说明 |
|---|---|
| `web/studio.html` | 低代码页面本体 |
| `web/studio/steps.js` | 步骤库（唯一真源，严格 JSON） |
| `pages/studio_steps.py` | 步骤库的测试端读取器（对标 `pages/i18n.py`） |
| `pages/studio_page.py` | Studio 的 Page Object |
| `studio/runner.py` | 场景校验、Gherkin 渲染、起 pytest、收产物 |
| `studio/server.py` | `StudioHandler(DemoApiHandler)`：web/ 静态 + `/studio/api/*` |
| `studio/bdd_report_plugin.py` | 每步结果记录插件（只在 Studio 运行时挂载） |
| `studio/__main__.py` | `python -m studio --port 8100` |
| `tests/test_dashboard_bdd.py` | pytest-bdd 步骤定义（唯一的执行实现） |
| `tests/features/` | 已提交的示例场景 + "保存为 feature"的落点 |
