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
--cov-report=xml:reports/coverage-py/coverage.xml
```

外加 [`.coveragerc`](.coveragerc) 里的两条，两条都是「不写就会让门禁静默判错」的：

- `relative_files = True`：让 XML 报告里的路径相对仓库根，而不是写死生成它的那台
  机器。没有它，在宿主机跑出的报告拿进容器里判，路径对不上，diff-cover 会安静地报
  "没有覆盖信息"并**退出码 0**——门禁不是判红，是直接放行。详见第六节。
- `concurrency = greenlet,thread`：Playwright 的**同步** API 每次 `click()` /
  `fill()` / `goto()` 都会切到 greenlet 上等 asyncio 的结果再切回来。coverage.py
  默认的 C 追踪器按帧维护数据栈，greenlet 切换绕过了它，**切回来之后该函数剩下的
  行不再记录**。`thread` 必须一起写：concurrency 一经指定就是整个白名单，只写
  greenlet 会关掉线程追踪，而 `server/app.py` 是 `demo_server` 夹具在 pytest 进程
  内用 ThreadingHTTPServer 起的（实测从 99% 掉到 35%）。同样详见第六节。

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
  同时生成可视化报告：**`reports/coverage-py/index.html`**（逐行绿/红染色源码），
  以及给机器读的 **`reports/coverage-py/coverage.xml`**（Cobertura）——第六节的
  增量门禁读的就是它。

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
   包含每段脚本的覆盖率汇总条与逐行染色源码；同时把同一份数据折算成逐行的
   Cobertura 报告 **`reports/coverage-js/coverage.xml`**（`write_cobertura()`），
   供第六节的增量门禁使用。

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

一次运行即产出两份可视化报告（各自还带一份同名的 `coverage.xml`）：

- Python 覆盖率：`reports/coverage-py/index.html`
- 前端 JS 染色：`reports/coverage-js/index.html`

只跑 API 测试：

```bash
.venv/bin/pytest tests/test_api.py
```

## 五、当前覆盖率快照（2026-09-08，150 个用例全通过）

本次快照在两侧各量了一遍并逐行一致：宿主机 macOS / Python 3.14（`.venv/bin/pytest`）
与容器 Linux / Python 3.12（`docker compose run --rm tests`）。这个"一致"是
`concurrency = greenlet,thread` 带来的，不是白拿的——见第二节与第六节"尺子这件事"。

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
- 前端 JS 总覆盖率 **93.3%**（24104 / 25826 可执行字符）。`web/studio.html`
  的主脚本 92.1%，随低代码 Studio 的加入自动进了这份报告——`js_coverage`
  夹具按页面 URL 采集，新页面不需要任何注册动作。染色报告能直观看出未覆盖
  的真实缺口，例如：
  - 各页面登录守卫的跳转分支（测试始终已登录，跳转不会发生），`studio.html`
    的守卫同理，只有 `test_studio_requires_auth` 会走到；
  - `dashboard.html` 的 logout 按钮处理器（现有登出测试只针对 `demo.html`）；
  - `profile.html` / `popup.html` 的守卫脚本按"红色但实际执行过"计入（附着
    时机限制，见第三节末尾）。

## 六、增量代码染色门禁（PR 的合并前提）

每个 PR 都拿 `git diff` 算出相对 base 分支的**改动行**，只对这些行判覆盖率，
要求 **100%**。存量欠账不追，新写的代码一行都不放过——这就是增量口径的全部意思。

### 口径

| 侧 | 分母 | 达不到 100% 时 |
| --- | --- | --- |
| Python（`server/` + `pages/`） | 第二节的 `--cov` 口径，一行不多 | **阻塞合并**，要人工审批才放行 |
| 前端内联 JS（`web/*.html`） | 第三节采集到的内联脚本 | 只报数字，不阻塞 |

JS 侧暂时不阻塞的理由就在第三节末尾：CDP 会话在新页面开始加载之后才附着，
`profile.html` / `popup.html` 的守卫脚本会被染成"红色但其实执行过"。拿这种假红去
卡合并是误杀。等这类缺口收敛了再改成阻塞。

分母是自然收窄的，不需要另写排除规则：Python 报告里只有 `server/` 和 `pages/`，
JS 报告里只有 `web/` 下的内联脚本。只动文档、CI、`tests/`、`studio/` 或 `perf/` 的
PR 分母为空，门禁直接判过。删掉的行不计入，只看新增和修改的行。

一个容易误会的点：**新加一个谁都没 import 的模块蒙混不过去**。`--cov=server` 是
目录口径，coverage.py 会把没被任何测试加载的文件也按 0% 写进报告（`server/__main__.py`
现在就是这样），它的每一行都是未染色的改动行。

### 怎么跑

```bash
docker compose run --rm tests            # 先跑测试，产出两份报告
docker compose run --rm tests coverage   # 再跑门禁
```

`coverage` 任务不替你跑测试——它读的是上一次 pytest 留在 `reports/` 里的东西：

| 读 / 写 | 谁产生的 |
| --- | --- |
| 读 `reports/coverage-py/coverage.xml` | `pytest.ini` 的 `--cov-report=xml` |
| 读 `reports/coverage-js/coverage.xml` | `scripts/js_coverage.py` 的 `write_cobertura()` |
| 写 `reports/diff-cover/python.{html,md}` | `diff-cover`，阻塞的那份 |
| 写 `reports/diff-cover/js.{html,md}` | `diff-cover`，参考的那份 |

对比哪个 base 由 `COVERAGE_BASE` 决定，默认 `origin/main`，CI 上填的是 PR 的 base：

```bash
COVERAGE_BASE=origin/main docker compose run --rm tests coverage
```

工作区里还没提交的改动（已暂存和未暂存的）都算在内，不必先 commit 才能看结果。
唯一的例外是**还没 `git add` 过的新文件**：diff-cover 默认不看未跟踪文件，所以本机
判过、CI 上却判不过是可能的——新建文件先 `git add` 一下再跑。

JS 侧那份 Cobertura 是把第三节的逐字符位图折算成逐行的：一行只要有**任一**个字符
染绿就算覆盖。取"任一"而不是"全部"是刻意的——V8 给的是块级区间，
`if (a) return b;` 这种一行里红绿混着是常态，严口径会把正常代码大面积判红。

### 达不到 100% 怎么办

首选当然是补测试。确实补不了（刻意保留的死代码、上面那种 V8 假红），就显式豁免——
两件事都要做，缺一样 `coverage-gate` 就是红的：

1. 给 PR 打上 **`coverage-waiver`** 标签；
2. 在 **PR 描述或任意一条评论**里写一行理由：

   ```
   豁免理由: server/__main__.py 只在 JMeter 压测下运行，pytest 永远走不到
   ```

   中英文冒号都认，也可以写成 `coverage-waiver: <理由>`；理由至少 10 个字，
   `豁免理由: 无` 这种挡得住。

3. 回到那次 run 点 **Re-run failed jobs**——只会重跑 `coverage-gate` 这一个 job，
   几秒钟。（标签是在 run 跑完之后加的，判定要重新读一次才看得到。）

转绿之后 run 的 summary 里会写明"本次合并使用了覆盖率豁免"、是谁写的理由、理由
原文和出处；`core.warning` 也会把它挂在 Actions 页面顶部。绕过这件事必须显式发生，
并且留下名字和理由。

`test` 只回答"测试过了吗"，"能不能合"的判定单独放在 `coverage-gate`，豁免才有地方
插进来。

### 这个门禁能保证什么、不能保证什么

**不能**：拦住合并。这个仓库是 Free 套餐的**私有**仓库，branch protection、rulesets、
以及私有仓库的 environment 保护规则都不开放——这三个 API 一律返回
`Upgrade to GitHub Pro or make this repository public`。没有必需状态检查，红叉在技术
上挡不住 Merge 按钮。

原本的设计是把豁免挂在受保护的 environment 上等 required reviewers 审批。在这个套餐
下那是个**假门**：没有保护规则的 environment 不拦任何人，job 直接通过，门禁会给出
一个"已通过人工审批"的绿色——比没有门禁更糟。所以改成了上面的标签 + 理由。

**能**：不达标时它是红的，而把它变绿必须是一个显式的、留了名字和理由的动作，不会在
无人注意时悄悄发生。标签能被作者自己打——在没有任何强制层的前提下，这是能做到的
上限：约束的是"绕过必须被看见"，不是"绕过不可能"。

要真正做到"100% 是 merge 的前提"，只有两条路：把仓库改成 **public**，或者升级到
**GitHub Pro**。任一之后，在 Settings → Branches 把 `coverage-gate` 加进必需状态检查
即可，工作流本身不用改。

### 顺带堵住的一个旧坑

`pytest.ini` 无条件开覆盖，而 `scripts/triage.py` 要为 30 个变异体各派生一次嵌套
pytest。以前每一次嵌套运行都会重写 `reports/coverage-py/` 和 `.coverage`，
`js_coverage` 夹具同样会重写 `reports/coverage-js/`——所以跑完
`docker compose run --rm all`，留在磁盘上的其实是**最后一个变异体**的覆盖报告，
不是全量套件的。现在两侧都堵上了：triage 的嵌套运行带 `--no-cov`，
`js_coverage_collector` 在 `--demo-html` 指向 `web/bugs/` 时不写报告。变异体运行的
覆盖数字本来就没有意义，而门禁正好读这些文件，不能让它们互相踩。

### 路径这件事，错了是"放行"不是"报错"

diff-cover 拿 XML 里的 `<source>` + `filename` 拼出路径，再和 `git diff` 报的文件名
比对。对不上的时候它不报错，而是说"No lines with coverage information in this diff"
然后**退出码 0**。也就是说，路径写错的门禁不会判红，会直接放行——比判错更难发现。

所以两侧的报告都刻意不带绝对路径：Python 侧靠 [`.coveragerc`](.coveragerc) 的
`relative_files`，JS 侧的 `write_cobertura()` 直接写 `<source>.</source>`。这样报告在
宿主机生成、进容器里判（CI 就是这么跑的，反过来也一样）结果都一致。改动这两处时请
连带验证一次：随便在 `server/` 里改一行不会被执行的代码，容器里跑 `coverage` 必须判红。

### 尺子这件事，错了是"误杀"——而且只在别人的机器上错

上面那条讲的是路径写错会**放行**；它有个镜像：**尺子本身量错会误杀**，并且只在
部分环境上误杀，所以更难发现。

Playwright 的同步 API 靠 greenlet 实现（每个 `click()` / `fill()` / `goto()` 切出去
等 asyncio、再切回来）。coverage.py 默认的 C 追踪器按帧维护数据栈，greenlet 切换绕
过了它——**切回来之后该函数剩下的行不再被记录**。症状极具迷惑性：150 个用例全绿，
报告却说 `login_page.login()` 只执行了第一行、`pages/` 里的 `return self` 一片未
覆盖。测试没问题，是尺子坏了。

跨环境的分裂让它更隐蔽：Python 3.14 起 coverage.py 默认走 sys.monitoring，不受
greenlet 影响，本机（macOS / 3.14）量出 `pages/` 100%；而容器与 CI 是 3.12，走 C
追踪器，同一份代码、同一批用例量出 `demo_page.py` 84%、`studio_page.py` 82%、总计
87%。门禁判的是**改动行 100%**，于是一个只改了 `pages/` 的正常 PR 会在 CI 上被判
红，理由是几行确实执行过的代码——本机复现不了。

修法就是 [`.coveragerc`](.coveragerc) 的 `concurrency = greenlet,thread`（见第二
节）。加上之后容器里的数字与本机逐行一致（见第五节快照）。

判断依据很好认：如果某个 `pages/` 方法「第一行覆盖、后面全红」，尤其是紧跟在一次
Playwright 调用之后的那行，那是尺子的问题，不是测试的问题——别去补测试，先看这条
配置还在不在。核对方式是同一套用例在 3.12 与 3.14 两侧跑出同一份 `term-missing`
行号，容器与宿主机各跑一次即可。

### 一个已知限制

`--cov=server --cov=pages` 让 XML 里的文件名相对各自的包目录（`app.py` 而不是
`server/app.py`），diff-cover 会把类节点同时按裸文件名和"每个 source 拼一遍"建索引，
于是**同名文件的行数据会被合并**。眼下撞名的只有两个空的 `__init__.py`，没有行，不
影响任何判定；但真要在 `pages/` 和 `server/` 下各放一个同名模块，得先把这个口径改掉。
JS 侧只有一个 source（`.`）加仓库相对文件名，没有这个问题。
