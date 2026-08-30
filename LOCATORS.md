# 定位器（Locator）策略

`pages/` 下的每一个定位器都取**该元素能达到的最高档位**，达不到时在代码注释里
写明降级原因。这套优先级只定义一次，在 [`pages/base_page.py`](pages/base_page.py)：

| 档位 | 定位方式 | 当前用量 |
|---|---|---|
| 1 | role + 可访问名称 — `get_by_role("button", name="Add")` | 13 |
| 2 | label / placeholder — `get_by_label` / `get_by_placeholder` | 0 |
| 3 | test id — `get_by_test_id`（专门埋的锚点） | 9 |
| 4 | CSS / XPath — `locator(...)` | 1 |

档位 1–2 定位的是用户或屏幕阅读器实际感知到的内容，所以这些测试同时也在验证
UI 的可访问性。**档位 1 必须要有可访问名称。** 一个有 role 但没有 accessible
name 的元素——没有 label 的 `<ul>`（role 是 `list`）、`<tr>`（role 是
`row`）、纯装饰性的 `<div>`——不满足档位 1，会正确地降级到 test id。仓库里那
9 个档位 3 的定位器，都是"确实没有可访问名称"的结果，不是遗漏。

唯一的档位 4 定位器是 `DemoPage.injected_script_count()`，它查找的是一个
`<script>` 标签——这里被断言的契约本身就是"标签名"，所以只能用结构选择器。

**不要凭记忆猜测 ARIA role——去实测。** Chromium 的可访问性树计算结果才是权
威，这里已经出现过一次和"背记忆答案"矛盾的情况：`<input type="password">`
的 role 计算结果确实是 `textbox`。判断某个档位是否可用之前，用
`locator.aria_snapshot()` 或 `get_by_role(...).count()` 实测。

有两点值得知道：

- **档位 1 把测试和"可见文案"绑在了一起**，所以文案只在一个地方维护——见下
  一节。`data-testid` 属性在 HTML 里始终保留，作为语义一旦回归时可以退回的
  档位 3 锚点。
- **`DashboardPage.error_message` 是"带但书的档位 1"。** 这个 `<p>` 标签在
  请求失败之前是 `display:none`，所以在默认态和成功态下它不在可访问性树
  里，`get_by_role("alert")` 在这两种状态下匹配到的是**零个**元素。现有的
  断言都是"它出现了 / 它显示了 X"这种形式，`expect()` 的重试机制能覆盖这种
  场景。但如果要断言"没有显示错误"，必须用 `to_have_count(0)`——
  `to_be_hidden()` 在元素被整个删除时也会通过，达不到验证目的。

结构性 CSS 选择器已经全部清除。曾经存在过的三个（`#chart .bar`、
`#stats-table tbody tr`、`#todo-list li`）都在一次不影响行为的改动中失效：
`.bar` 同时也是一个*样式*类，另外两个把 `<table>` / `<ul><li>` 的 DOM 结构
硬编码进了选择器。待办事项现在通过 ARIA `listitem` role 定位，即使外层换成
别的标签依然能找到。

`web/dashboard.html` 图表柱子上的 `data-value` 是一个刻意保留、并在代码注释
里写明的**测试契约**：图表重新实现时必须保留它，但渲染方式本身可以随便改。

## 与文案目录（`web/i18n/catalog.js`）的关系

档位 1 的定位器绑定的是可见文案，正常来说意味着改一个按钮文案就会悄悄弄挂测
试。`web/i18n/catalog.js` 是唯一的事实来源，同时被两边读取：

- **浏览器端**通过 `web/i18n/apply.js`，在 `DOMContentLoaded` 时给每个
  `[data-i18n]` / `[data-i18n-placeholder]` 元素填充文案；
- **测试端**通过 `pages/i18n.py`，解析同一份文件。

Page Object 里从不直接写死文案，只会要一个 key：

```python
self.add_btn = page.get_by_role("button", name=t("addTodo", locale))
```

改按钮文案因此只需要改一处。`tests/test_i18n.py` 用行为而不是断言来证明这一
点：同一套 Page Object 驱动同样的交互，跑遍目录里的每个 locale（目前是 `en`
和 `zh`），过程中只有 `window.__locale` 在变化。一个 parity 测试保证各
locale 的 key 集合一致，另一个测试保证没有两个 locale 共享同一段翻译——否则
一个"加了但没真正翻译"的 locale 会让测试通过却什么都没验证到。

目录用 `.js` 而不是 `.json`，是为了让页面能用普通 `<script>` 标签加载——不
经过 `fetch`，也就不存在"档位 1 定位器在文案填充之前跑起来"的时间窗口。它的
对象字面量是严格 JSON，这也是 `pages/i18n.py` 能够直接读取而不用另外维护一
份数据、也不用引入构建步骤的原因。`t()` 遇到未知 key 或 locale 会直接抛错，
而不是静默回退——静默回退只会让问题在很久之后，以"某个定位器莫名其妙匹配不
到任何东西"的形式重新出现。

范围上只收录**定位器或断言依赖的文案**。`web/demo.html` 里状态标签、计数
器、待办项渲染的文案故意没有收录——那正是 `web/bugs/*.html` 变异体专门破坏
的那部分 JS，重写它会让这些故意注入的缺陷失去意义。详见
[`AGENTS.md`](AGENTS.md) 第 1 节和第 4 节。
