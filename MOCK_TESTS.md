# Mock 测试说明文档

本文档说明 [`tests/test_dashboard.py`](tests/test_dashboard.py) 中所有基于 Playwright `page.route()` 的网络请求 Mock 测试：每个测试模拟了什么场景、如何模拟、以及验证了什么效果。

## 背景

[`web/dashboard.html`](web/dashboard.html) 页面加载后会调用 `fetch('/api/stats')` 获取周数据，并渲染成柱状图 + 表格 + 合计（总和）。

- **默认（不 mock）**：本地测试服务器（`tests/conftest.py` 中的 `DemoRequestHandler`）会对 `/api/stats` 返回一份固定的 JSON 数据，所以页面本身脱离 Playwright 也能正常工作。
- **Mock 模式**：测试在 `page.goto()` 之前调用 `page.route("**/api/stats", ...)` 拦截这个请求，替换成任意想要的响应内容——用来构造真实后端不方便随时复现的场景（空数据、报错、超大数据集、加载中等）。

页面对应的状态元素（用于测试断言）：

| 元素 | 含义 |
|---|---|
| `#loading` | 请求进行中 |
| `#chart-container` / `.bar` | 正常渲染出的柱状图 |
| `#empty-message` | 空数据状态 |
| `#error-message` | 错误状态 |

## 测试一览

| # | 测试名称 | Mock 方式 | 模拟场景 | 验证内容 |
|---|---|---|---|---|
| 1 | `test_dashboard_uses_real_backend_when_unmocked` | 不设置任何 route，直接访问 | 真实后端（本地服务器默认返回的固定数据） | 柱状图数值 `[12,19,3,5,2]`、合计 `41`、表格 5 行 —— 证明"不 mock 也能正常工作" |
| 2 | `test_dashboard_renders_mocked_chart_data` | `route.fulfill(json={...})` 返回自定义数据 | 正常的 mock 数据响应 | 柱状图/合计/表格行数与 mock 数据完全一致 |
| 3 | `test_dashboard_shows_empty_state_when_no_data` | `route.fulfill(json={"labels": [], "values": []})` | 后端返回空数组 | 页面显示"空数据"提示，不渲染柱子 |
| 4 | `test_dashboard_shows_error_state_on_api_failure` | `route.fulfill(status=500, body=...)` | 后端返回 HTTP 500 | 页面显示错误提示，错误文案里包含状态码 `500` |
| 5 | `test_dashboard_refresh_button_refetches_data` | 用一个计数器，第 1 次请求返回数据集 A，第 2 次（点击 Refresh 后）返回数据集 B | 点击"刷新"按钮重新拉取数据 | 刷新前后柱状图分别对应两份不同的 mock 数据 |
| 6 | `test_dashboard_shows_network_error_on_aborted_request` | `route.abort()` | 连接级失败（DNS 失败/连接被拒/断网），区别于 HTTP 层的错误响应 | 页面显示错误提示，错误文案是"network error"而非状态码 |
| 7 | `test_dashboard_shows_error_on_malformed_json_response` | `route.fulfill(status=200, body="not valid json")` | 后端返回 200 但 body 不是合法 JSON | `response.json()` 解析抛异常，页面同样落到错误状态 |
| 8 | `test_dashboard_handles_all_zero_values_without_crashing` | `route.fulfill(json={"values": [0,0,0], ...})` | 数据条数不为 0，但每个值都是 0 | 页面**不**误判为"空数据"，柱子高度为 0 渲染但不崩溃（验证图表计算里除以 0 的边界处理） |
| 9 | `test_dashboard_renders_large_dataset` | `route.fulfill(json={...})` 返回 12 组数据（Month1~Month12） | 数据量较大的场景 | 柱状图/表格能正确渲染 12 条数据，合计值正确 |
| 10 | `test_dashboard_shows_loading_state_while_request_is_pending` | 拦截请求但**先不 `fulfill`**，把 `Route` 对象暂存下来，等断言完"加载中"状态可见后再手动调用 `route.fulfill()` 完成请求 | 请求一直处于"进行中" | 在数据返回之前，`#loading` 确实可见；随后手动放行请求，图表正常渲染 |
| 11 | `test_dashboard_refresh_cycles_through_three_mock_datasets` | 同 #5，但准备 3 份数据集，点击 2 次刷新 | 连续多次刷新 | 每次刷新后图表都对应正确的那一份 mock 数据 |

## 踩过的坑：如何正确模拟"加载中"状态

最初尝试用 `time.sleep(0.5)` 放在 route 回调里模拟延迟响应，结果 `dashboard.loading.is_visible()` 断言失败——因为 `time.sleep()` 会阻塞 Playwright 同步 API 用来和浏览器通信的那个线程，导致 `page.goto()` 一直等到 `time.sleep` 结束、请求完成之后才返回，根本来不及观察到中间的"加载中"状态。

正确写法（见测试 #10）：在 route 回调里**只捕获 `Route` 对象、不调用任何完成方法**（`fulfill`/`continue_`/`abort`），这样请求会一直挂起；测试代码断言完加载状态可见后，再显式调用 `route.fulfill()` 把请求"放行"。这是 Playwright 官方推荐的、用来测试加载态/骨架屏的标准模式。

## 如何运行

```bash
source .venv/bin/activate
pytest tests/test_dashboard.py -v
```

只看某一类场景，例如只跑 mock 相关的：

```bash
pytest tests/test_dashboard.py -v -k "mock or error or empty or loading or refresh"
```
