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

API 测试覆盖：正常路径、鉴权失败（缺 token / 错 token）、参数校验（缺字段、
空文本、纯空白、类型错误、超长）、非法 JSON 请求体、404 与非法 id 等错误分支。

## 二、Python 侧染色：pytest-cov（coverage.py）

`pytest.ini` 的 `addopts` 中固定开启：

```
--cov=server --cov=pages --cov-report=term-missing --cov-report=html:reports/coverage-py
```

- coverage.py 通过 Python trace 钩子对 `server/`（后端）和 `pages/`（Page Object）
  的每一行做染色标记，API 测试与 UI 测试共同贡献覆盖。
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

## 五、当前覆盖率快照（2026-08-25，54 个用例全通过）

- Python 总覆盖率 **100%**（`server/app.py` 与 `pages/` 全部 100%）。
  值得一提：最初有几条「非法 JSON 请求体」分支没有覆盖到——Playwright 的
  `data=` 传字符串时会被序列化成合法 JSON，改用 `data=b"..."` 原样发送字节
  后才真正命中服务端的 JSON 解析异常分支。这正是染色报告的价值所在。
- 前端 JS 总覆盖率 **91.1%**。染色报告能直观看出未覆盖的真实缺口，例如：
  - `dashboard.html` 的登录守卫跳转分支（测试始终已登录，跳转不会发生）；
  - `dashboard.html` 的 logout 按钮处理器（现有登出测试只针对 `demo.html`）。
