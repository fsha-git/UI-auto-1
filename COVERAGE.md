# API 测试与覆盖率（代码染色）

本项目在 UI 测试之外增加了纯 API 测试，并对**后端 Python 代码**和**前端内联 JS**
两侧进行代码染色（instrumentation），统计测试覆盖率并生成可视化 HTML 报告。

## 一、API 测试

- 被测后端：[`server/app.py`](server/app.py)。原先只在测试夹具里 mock 的
  `/api/stats` 被抽取成一个真正的后端模块（静态文件 + JSON API），
  测试服务器（`tests/conftest.py` 的 `demo_server` 夹具）直接挂载它，
  **在 pytest 进程内运行**——这也是 Python 侧覆盖率能统计到它的前提。
- 测试文件：[`tests/test_api.py`](tests/test_api.py)，使用 Playwright 的
  `APIRequestContext`（`api_request_context` 夹具），不启动浏览器。

接口清单：

| 接口 | 说明 |
| --- | --- |
| `GET /api/health` | 健康检查 |
| `POST /api/login` | 登录校验（demo / demo123），返回 token；401 / 400 错误分支 |
| `GET /api/stats` | dashboard 的周统计数据 |
| `GET /api/todos` | 列出待办（需要 `Authorization: Bearer <token>`） |
| `POST /api/todos` | 新增待办（鉴权 + 文本校验：非空、去首尾空白、长度上限） |
| `DELETE /api/todos/<id>` | 删除待办（鉴权；404 / 400 错误分支） |
| `GET /api/profile` | 当前账号的用户名 + 实时待办数（鉴权；被 `web/profile.html` 消费） |

API 测试覆盖：正常路径、鉴权失败（缺 token / 错 token）、参数校验（缺字段、
空文本、纯空白、类型错误、超长）、非法 JSON 请求体、404 与非法 id 等错误分支。

## 二、Python 侧染色：pytest-cov（coverage.py）

`pytest.ini` 的 `addopts` 中固定开启：

```
--cov=server --cov=pages --cov-report=term-missing --cov-report=html:reports/coverage-py
```

- coverage.py 通过 Python trace 钩子对 `server/`（后端）和 `pages/`（Page Object）
  的每一行做染色标记，API 测试与 UI 测试共同贡献覆盖。
- **染色目标只包含被测应用和 Page Object，不包含工装。** `scripts/`（变异测试
  与 JS 染色采集器）和 `studio/`（低代码 Studio 的运行器，见
  [`STUDIO.md`](STUDIO.md)）都不在 `--cov` 里：它们是跑测试的工具，不是被测对
  象，把它们算进来只会让这个数字变得没法解读。`studio/` 里的纯逻辑部分（步骤
  库、Gherkin 渲染、场景校验、产物路径守卫、HTTP 接口）由
  [`tests/test_studio_backend.py`](tests/test_studio_backend.py) 无浏览器覆盖，
  只是不进这份报告。
- 每次 `pytest` 结束后终端打印逐文件的覆盖率与未覆盖行号（`term-missing`），
  同时生成可视化报告：**`reports/coverage-py/index.html`**（逐行绿/红染色源码）。

## 三、前端 JS 染色：V8 精确覆盖（CDP）

前端页面是 `web/*.html` 里的内联 `<script>`，Python 覆盖工具管不到它们。
做法（见 [`scripts/js_coverage.py`](scripts/js_coverage.py) 与
`tests/conftest.py` 中的 `js_coverage` 夹具）：

1. 每个 UI 测试开始时，对该测试用到的每个 Playwright 页面挂一个 CDP 会话，
   开启 `Profiler.startPreciseCoverage`（块级精确覆盖），同时监听
   `Debugger.scriptParsed` 记录每段内联脚本在 HTML 文件中的行列位置；
2. 测试结束时 `Profiler.takePreciseCoverage` 拿到字符区间级的执行计数，
   按「内层区间覆盖外层」的 V8 语义折算成逐字符的三态位图
   （绿=执行过 / 红=从未执行 / 无色=V8 未报告的空白与注释）；
3. 同一段脚本在整个测试会话内跨用例合并（任一用例执行过即算覆盖）；
4. 会话结束时生成染色报告：**`reports/coverage-js/index.html`**，
   包含每段脚本的覆盖率汇总条与逐行染色源码。

纯 API 测试不涉及页面，该夹具自动跳过。

**运行时新开页面（弹窗 / 新标签页）的采集**：测试过程中由 `window.open()` /
`target=_blank` 产生的新页面，通过 context 的 `"page"` 事件监听器补挂 CDP
会话。这里有两个 V8 层面的坑（详见 `JsCoverageCollector.collect_all` 的注
释）：弹窗与 opener 共享同一个 renderer 进程（同一 isolate），
`Profiler.takePreciseCoverage` 会把**整个 isolate** 的待取覆盖一次抽干——谁
先取谁拿到全部页面的条目；而每个会话的 `Debugger.scriptParsed` 只描述自己页
面的脚本。因此同一测试的所有会话必须**合并成一次采集**：覆盖条目对照所有会
话 scriptParsed 元数据的并集解析（script id 只在单个 isolate 内唯一，跨会话
查找时还要求 URL 一致才采信）。残余限制：会话在新页面开始加载后才附着，附着
前已跑完的顶层语句可能染成"红色但实际执行过"，所以 `tests/test_windows.py`
保留了对 `profile.html` 的直接导航用例（走预先插桩的 `page` 夹具）作为可靠
锚点。

## 四、运行方式

```bash
.venv/bin/pytest
```

一次运行即产出两份可视化报告：

- Python 覆盖率：`reports/coverage-py/index.html`
- 前端 JS 染色：`reports/coverage-js/index.html`

只跑 API 测试：

```bash
.venv/bin/pytest tests/test_api.py
```

## 五、当前覆盖率快照（2026-09-01，141 个用例全通过）

- Python 侧 `server/app.py` 99%、`pages/` 除 `popup_page.py`（95%）外全部
  100%（含新增的 `pages/studio_page.py` 与 `pages/studio_steps.py`）。两处未
  覆盖行均属已知且合理：`server/app.py` 的 `fake_function`（故意保留的死代
  码，见 AGENTS.md）；`popup_page.py` 里 `wait_for_close()` 的
  `wait_for_event` 行——测试先断言 opener 侧结果再等关闭，届时弹窗通常已经
  自关，`is_closed()` 守卫直接短路，该行是否执行取决于竞态时序，不值得为凑
  数字而改断言顺序。
  值得一提：最初有几条「非法 JSON 请求体」分支没有覆盖到——Playwright 的
  `data=` 传字符串时会被序列化成合法 JSON，改用 `data=b"..."` 原样发送字节
  后才真正命中服务端的 JSON 解析异常分支。这正是染色报告的价值所在。
- 前端 JS 总覆盖率 **92.4%**（22070 / 23883 可执行字符）。`web/studio.html`
  的主脚本 90.0%，随低代码 Studio 的加入自动进了这份报告——`js_coverage`
  夹具按页面 URL 采集，新页面不需要任何注册动作。染色报告能直观看出未覆盖
  的真实缺口，例如：
  - 各页面登录守卫的跳转分支（测试始终已登录，跳转不会发生），`studio.html`
    的守卫同理，只有 `test_studio_requires_auth` 会走到；
  - `dashboard.html` 的 logout 按钮处理器（现有登出测试只针对 `demo.html`）；
  - `profile.html` / `popup.html` 的守卫脚本按"红色但实际执行过"计入（附着
    时机限制，见第三节末尾）。
