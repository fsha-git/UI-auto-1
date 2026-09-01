# 定位器（Locator）策略

`pages/` 下的每一个定位器都取**该元素能达到的最高档位**，达不到时在代码注释里
写明降级原因。这套优先级只定义一次，在 [`pages/base_page.py`](pages/base_page.py)：

| 档位 | 定位方式 | 当前用量 |
|---|---|---|
| 1 | role + 可访问名称 — `get_by_role("button", name="Add")` | 33 |
| 2 | label / placeholder — `get_by_label` / `get_by_placeholder` | 2 |
| 3 | test id — `get_by_test_id`（专门埋的锚点） | 31 |
| 4 | CSS / XPath — `locator(...)` | 3 |

（用量是从代码里数出来的，不是手工累加的：
`grep -rn "get_by_role" pages/ | grep -v ':[0-9]*: *#' | wc -l`，其余档位同理，
过滤掉的是 `base_page.py` 里用 `get_by_role("button", name="Add")` 举例说明
的注释行。）

档位 1–2 定位的是用户或屏幕阅读器实际感知到的内容，所以这些测试同时也在验证
UI 的可访问性。**档位 1 必须要有可访问名称。** 一个有 role 但没有 accessible
name 的元素——没有 label 的 `<ul>`（role 是 `list`）、`<tr>`（role 是
`row`）、纯装饰性的 `<div>`——不满足档位 1，会正确地降级到 test id。仓库里那
31 个档位 3 的定位器，都是"确实没有可访问名称"的结果，不是遗漏。

档位 2 目前只有两处，都在 [`pages/studio_page.py`](pages/studio_page.py)：低代码
Studio 的"场景名称"输入框，以及步骤面板里每个参数的输入框。它们各自有真正的
`<label for=…>`，但没有值得绑定的 role + 名称组合（`textbox` 的名称就来自
label，占位符则是更弱的来源），所以恰好落在档位 2 而不是被迫降到 test id。

档位 4 定位器只有三个，各自的契约都不是 DOM 结构：
`DemoPage.injected_script_count()` 查找的是一个 `<script>` 标签——被断言的契
约本身就是"标签名"；`DemoPage.chart_point()` / `chart_series_points()` 用的
是 `[data-testid="chart-point"][data-series=…][data-index=…]` 这样的**属性组
合**——趋势图的隐藏数据镜像节点没有 role 也没有名称，且这些 `data-*` 属性本
身就是写进 `web/demo.html` 注释里的测试契约（见下文）。

**不要凭记忆猜测 ARIA role——去实测。** Chromium 的可访问性树计算结果才是权
威，这里已经出现过一次和"背记忆答案"矛盾的情况：`<input type="password">`
的 role 计算结果确实是 `textbox`。判断某个档位是否可用之前，用
`locator.aria_snapshot()` 或 `get_by_role(...).count()` 实测。

有三点值得知道：

- **档位 1 把测试和"可见文案"绑在了一起**，所以文案只在一个地方维护——见下
  一节。`data-testid` 属性在 HTML 里始终保留，作为语义一旦回归时可以退回的
  档位 3 锚点。
- **`DashboardPage.error_message` 和 `ProfilePage.error_message` 是"带但书
  的档位 1"。** 这两个 `<p>` 标签在请求失败之前是 `display:none`，所以在默认
  态和成功态下它们不在可访问性树里，`get_by_role("alert")` 在这两种状态下匹
  配到的是**零个**元素。现有的断言都是"它出现了 / 它显示了 X"这种形式，
  `expect()` 的重试机制能覆盖这种场景。但如果要断言"没有显示错误"，必须用
  `to_have_count(0)`——`to_be_hidden()` 在元素被整个删除时也会通过，达不到
  验证目的。
- **`StudioPage` 的档位 1 名称有两个来源，都不是硬编码。** 工具栏按钮
  （运行 / 清空 / 保存 / 打开 Trace）的名称来自 `pages/i18n.py`，和其它页面
  一样；但**步骤面板每个参数输入框的 label 文案来自
  [`pages/studio_steps.py`](pages/studio_steps.py)**——参数名是步骤库
  `web/studio/steps.js` 里的数据，不是 UI 文案，所以不进 i18n 目录，也不需要
  翻译。同一个道理，`StudioPage.palette_step()` 给每个步骤埋的是**逐步骤的
  test id**（`palette-step-<步骤 id>`）而不是共享 test id 加一个
  `[data-step-id=…]` 的 CSS 过滤——后者会把这个定位器推到档位 4，而这里完全
  没有必要。另外 Studio 的两个面板互相 `display:none`，所以隐藏面板里的按钮
  在可访问性树里同样是**零个**元素（和上面 `role=alert` 是同一个陷阱）：测试
  必须先切到对应标签页，才能定位到该面板里的控件。

结构性 CSS 选择器已经全部清除。曾经存在过的三个（`#chart .bar`、
`#stats-table tbody tr`、`#todo-list li`）都在一次不影响行为的改动中失效：
`.bar` 同时也是一个*样式*类，另外两个把 `<table>` / `<ul><li>` 的 DOM 结构
硬编码进了选择器。待办事项现在通过 ARIA `listitem` role 定位，即使外层换成
别的标签依然能找到。

`web/dashboard.html` 图表柱子上的 `data-value` 是一个刻意保留、并在代码注释
里写明的**测试契约**：图表重新实现时必须保留它，但渲染方式本身可以随便改。
`web/demo.html` 的趋势图（Canvas）把同样的思路推广了一步：Canvas 像素无法被
定位器查询，所以图表把每个绘制点镜像成 `#chart-data` 下的隐藏节点
（`data-series` / `data-index` / `data-value` / `data-px` / `data-py`），并在
tooltip 和 canvas 元素上发布 `data-*` 状态（`data-series-count` /
`data-generation`）。这些属性同样是注释写明的测试契约。另外
`DemoPage.expect_tooltip_hidden()` 先断言 `to_have_count(1)` 再断言
`to_be_hidden()`——tooltip 元素设计上**始终存在于 DOM 里**，只靠 `hidden`
属性切换，但 `to_be_hidden()` 单用在元素被整个删除时同样会通过（正是上面
`role=alert` 的那个陷阱），count 检查把"隐藏"钉死为"还在 DOM 里且不可见"。

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

同一套做法被用了两次：[`web/studio/steps.js`](web/studio/steps.js) 是低代码
Studio 的步骤库，也是一个 `.js` 文件、也用普通 `<script>` 标签加载、里面也是
严格 JSON，测试端由 [`pages/studio_steps.py`](pages/studio_steps.py) 解析。理由
一样：一句 Gherkin 被四方读取（Studio 页面、`pages/studio_page.py`、
`tests/test_dashboard_bdd.py` 的步骤定义、`studio/runner.py` 的 feature 渲染
器），只有单一定义点才不会对不上。细节见 [`STUDIO.md`](STUDIO.md)。

范围上只收录**定位器或断言依赖的文案**。`web/demo.html` 里状态标签、计数
器、待办项渲染的文案故意没有收录——那正是 `web/bugs/*.html` 变异体专门破坏
的那部分 JS，重写它会让这些故意注入的缺陷失去意义。详见
[`AGENTS.md`](AGENTS.md) 第 1 节和第 4 节。
