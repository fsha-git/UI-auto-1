# JMeter 负载 / 压力 / 并发测试

用 JMeter 对 `server/app.py` 的 `/api/*` 接口做六类非功能测试：性能基线、阶梯加压定容量、尖峰、长稳（soak）、压力、并发。

前端渲染性能不在 JMeter 覆盖范围内，由 `tests/test_frontend_perf.py` 单独兜底（见文末）。

## 前置条件

```bash
brew install jmeter   # 依赖的 openjdk 已随 Homebrew 提供
```

无需手动配置 JAVA_HOME：`perf/run_perf.sh` 在未设置时会自动指向 `/opt/homebrew/opt/openjdk@21`。

## 独立压测账号

压测**不使用** pytest 的 `demo` 账号。`perf/accounts.csv` 提供 50 个专用账号（`perfuser01..50`），由 `run_perf.sh` 通过 `python -m server --accounts perf/accounts.csv` 注册。

`server/app.py` 的 `todo_store` 按账号分区：一个账号既看不到也删不掉另一个账号的 todo（`tests/test_api.py` 里有对应断言）。共用单一身份时这类隔离缺陷在结构上就测不出来，压测线程之间也会争抢本不该互相可见的数据。

各场景的账号策略不同，是刻意的：

| 场景 | 账号 | 原因 |
|---|---|---|
| performance / stress / stepload / spike / soak | CSV Data Set 轮询 50 个账号（`shareMode=all`, `recycle=true`） | 模拟真实的多用户混合流量 |
| concurrency | 固定单账号 `${__P(account,perfuser01)}` | 集合点要的是**同一分区上的最大锁竞争**；且 tearDown 的"该账号 store 为空"断言只有在所有线程都写同一账号时才有意义 |

换账号文件：`PERF_ACCOUNTS=my_accounts.csv perf/run_perf.sh all`。

## 独立启动服务

pytest 夹具（`tests/conftest.py` 的 `demo_server`）用随机端口在进程内起服务，JMeter 无法复用。为此新增了独立入口，与夹具互不影响：

```bash
.venv/bin/python -m server --port 8000
```

该入口对负载做了两处必要调优（只影响压测入口，pytest 夹具行为不变）：

- **HTTP/1.1 keepalive**（`KeepAliveHandler`）：`BaseHTTPRequestHandler` 默认 HTTP/1.0，每个请求都关连接。压测下客户端每秒新建数千连接，很快耗尽本地临时端口（大量 `BindException: Can't assign requested address`）。启用 keepalive 后同机吞吐量从约 3,000 req/s（52% 连接错误）提升到约 12,000 req/s（0 错误）。
- **accept backlog 128**（`LoadTestServer`）：默认 backlog 为 5，集合点场景 50 线程同时建连会溢出导致连接超时。

注意：`server/__main__.py` 只在压测时运行，不被 pytest 覆盖，因此在 pytest-cov 覆盖率报告中显示未覆盖属预期。

## 一键运行

```bash
perf/run_perf.sh all            # performance / stress / stepload / spike / concurrency
perf/run_perf.sh performance    # 只跑某一类
perf/run_perf.sh soak           # 默认 30 分钟，不含在 all 里，需单独跑
```

脚本会：检查 jmeter → **每类测试启动全新 server 进程**（注册压测账号，保证 `todo_store` 为空、id 从 1 开始）→ `jmeter -n` 无 GUI 运行 → 生成 HTML dashboard → 用 `perf/check_jtl.py` 做阈值校验 → kill server。任一类失败则退出码非零。

额外参数直接透传给 jmeter，可覆盖 JMX 中的默认值：

```bash
perf/run_perf.sh stress -Jthreads=300 -Jduration=300
```

```bash
perf/run_perf.sh concurrency -Jthreads=100 -Jrendezvous=100 -Jloops=20
```

端口冲突时用 `PERF_PORT=8001 perf/run_perf.sh all` 换端口。

## 六个测试场景

| 场景 | JMX | 默认参数 | 流程 | 通过标准 |
|---|---|---|---|---|
| 性能基线（load） | `perf/performance.jmx` | threads=20, rampup=10s, duration=60s，思考时间 100–300ms | 登录一次 → 循环 health / stats / 查 todos / 建 todo(201) / 删 todo(204) | 错误率 ≤1%，p95 ≤800ms，吞吐 ≥50 req/s |
| 阶梯加压（capacity） | `perf/stepload.jmx` | step_threads=50, step_seconds=60（4 级：50→100→150→200） | 4 个线程组错开 delay 启动、同时结束，每级稳定保持 60s | 错误率 ≤5%，5xx =0；**主要产出是每级的 p95/吞吐**，用于定拐点 |
| 尖峰（spike） | `perf/spike.jmx` | 基线 20 线程 180s + 第 60s 起 300 线程冲 30s | 基线组全程稳定跑，尖峰组中途 5s 内加满再撤走 | 错误率 ≤2%，5xx =0；看基线延迟的**恢复速度** |
| 长稳（soak） | `perf/soak.jmx` | threads=20, rampup=30s, duration=1800s，带思考时间 | 与性能基线同流程，持续 30 分钟 | 错误率 ≤0.5%，5xx =0，吞吐 ≥40 req/s；看延迟/吞吐是否随时间漂移 |
| 压力（线性加压） | `perf/stress.jmx` | threads=200, rampup=120s, duration=180s，无思考时间 | 同上（最大压力） | 错误率 ≤10%，5xx =0；延迟仅作观察 |
| 并发（集合点） | `perf/concurrency.jmx` | threads=50, rendezvous=50, loops=10, rampup=2s，固定单账号 | POST 和 DELETE 各挂 SyncTimer，50 线程同时发起；tearDown 校验该账号 todos 为空 | 错误率 =0，5xx =0，结束时 store 为空 |

`stepload.jmx` 只用 JMeter 自带元件实现阶梯：4 个 ThreadGroup 用 `ThreadGroup.delay` 错开启动、用 `${__jexl3(...)}` 算出各自时长以便同时结束，因此**不依赖 jmeter-plugins**。

所有场景公共部分：`OnceOnlyController` 登录一次提取 token，线程组级 HeaderManager 注入 `Authorization: Bearer ${token}`，每个请求都断言响应码。登录失败的线程会被 Result Status Action Handler 直接终止 —— 否则该线程终身没有 token，后续每次迭代都产生 401，把真实错误率放大几个数量级（首轮压测中 126 个登录失败级联出了 11 万个 401）。

并发场景的 rampup=2s 是刻意的：集合点由 SyncTimer 保证（线程在集合点等齐后同时发请求），建连可以平缓进行，避免把"同时建连打爆 backlog"误报成锁的问题。

### 各场景设计意图

- **性能基线**：带思考时间模拟 20 个真实用户的混合读写流量，从 dashboard 读吞吐量和 p50/p95/p99 延迟作为基线。POST 与 DELETE 配对，测试自清理。
- **阶梯加压**：线性 ramp 的问题是每个并发档位只被扫过一瞬间，读不出"这个档位能稳住多少吞吐"。阶梯让每级保持整整 60s，Response Times Over Time 图上会出现清晰的四段平台，拐点就是平台开始抬头的那一级。
- **尖峰**：真实事故往往不是缓慢加压，而是突发流量。基线组提供参照系，尖峰组撤走后基线延迟多久回到原位，就是系统的**恢复能力**——只有稳态压测是看不到这个指标的。
- **长稳**：30 分钟低压恒定负载，专门抓随时间累积的问题（内存/句柄泄漏、连接池耗尽、缓存无限增长）。判据不是绝对延迟，而是**延迟和吞吐是否随时间漂移**。
- **压力**：120 秒线性加压到 200 线程再保持 60 秒，无思考时间。在 dashboard 的 Response Times Over Time / Codes per Second 图上找性能拐点。
- **并发**：SyncTimer 让 N 个线程在集合点同时发出 POST（再同时 DELETE），冲击 `TodoStore` 的 `threading.Lock` 与 `_next_id` 分配。DELETE 出现 404 即意味着两个线程拿到同一 id（锁失效）；tearDown 线程组最后 GET `/api/todos` 断言 `"todos": []`，验证无丢失更新。

## 报告解读

每类测试输出在 `reports/jmeter/<type>/`（已 gitignore）：

- `dashboard/index.html` — JMeter HTML 报告：APDEX、Statistics 表（含各百分位延迟）、Response Times Over Time（压力测试看拐点）、Codes per Second（错误爆发点）。
- `results.jtl` — 原始 CSV 样本，`check_jtl.py` 的输入（勿改成 XML 格式）。
- `jmeter.log` / `server.log` — 排障用。

`perf/check_jtl.py` 也可单独跑：

```bash
.venv/bin/python perf/check_jtl.py reports/jmeter/performance/results.jtl --max-error-rate 1 --max-p95 800
```

### 趋势看板（跨运行对比）

单次报告会被下一次运行覆盖，跨运行数据由两个追加式产物保留：

- `reports/jmeter/history.jsonl` — 每次运行（含失败）由 `perf/record_run.py` 追加一行：时间戳、场景、**实际生效参数**（JMX 默认值叠加 `-J` 覆盖）、阈值、`check_jtl.py` 全部指标、`statistics.json` 的每请求统计、通过/失败。存放路径可用 `PERF_HISTORY` 环境变量覆盖；删除 `reports/` 即清空历史。
- `reports/jmeter/perf_dashboard.html` — **性能趋势看板**，每次 `run_perf.sh` 结束时由 `perf/make_dashboard.py` 自动重新生成（也可单独跑）。自包含 HTML，浏览器直接打开（file:// 即可）：每场景最新结果摘要卡、吞吐量 / p95+p99 延迟 / 错误率三条趋势图（悬浮数据点可看该次参数，失败运行为红色空心点，指标缺失为 ×）、历次运行明细（参数、阈值、每请求统计，最新一次可跳转 JMeter 完整报告）。

```bash
.venv/bin/python perf/make_dashboard.py   # 默认读写 reports/jmeter/ 下的 history.jsonl 与 perf_dashboard.html
```

### 回归门禁（相对基线）

固定阈值只能拦住"绝对值超标"，拦不住"仍在阈值内、但相对历史明显劣化"。`check_jtl.py` 因此还会和 `history.jsonl` 里**同场景、且通过的**历史运行的中位数比较：

```bash
.venv/bin/python perf/check_jtl.py reports/jmeter/performance/results.jtl \
    --baseline reports/jmeter/history.jsonl --baseline-type performance \
    --max-regression-pct 25
```

`run_perf.sh` 每次都会自动带上这三个参数（回归百分比可用 `PERF_MAX_REGRESSION_PCT` 覆盖，默认 25%）。两个保护开关是必需的，否则门禁不可用：

- `--min-baseline-runs`（默认 3）：一次历史运行是样本不是基线，拿它做门禁只会把正常的运行间波动变成红色构建。
- `--regression-floor-ms`（默认 20）：本机回环下 p95 常年 1–2ms，一毫秒的调度抖动就是"+100% 回归"。基线 p95 低于该下限时只保留绝对阈值 `--max-p95`。

首次跑某个场景时没有基线，门禁自动跳过，输出里会打印 `[gate off: ...]`。

## 结果有效性边界

以下限制会实质影响数字的解读，看报告前必须知道：

1. **压测机与被测服务同机、走 loopback。** 客户端和服务端抢同一批 CPU，网络栈被完全绕过。这里的绝对延迟数字**不能**外推到真实部署。
2. **`ThreadingHTTPServer` 每连接一线程，它本身就是主要瓶颈。** 到 200 线程仍未出现 5xx，说明拐点是被测**装置**的拐点，不是应用逻辑的拐点。
3. **因此这套压测的价值主要在"相对"而非"绝对"**：跨版本的趋势对比、并发正确性（集合点）、以及回归门禁。要拿绝对容量数字，需要把负载机和被测服务分离到不同主机，并换掉 `ThreadingHTTPServer`。

## 前端渲染性能

JMeter 只压 API。`dashboard.html` 渲染 500 根柱 + 500 行表格的开销由 `tests/test_frontend_perf.py` 兜底，随 pytest 一起跑：

```bash
pytest tests/test_frontend_perf.py -v     # 只跑前端性能
pytest -m "not perf"                      # 跑其余测试，跳过性能护栏
```

三个用例分别管：单次大数据集渲染预算、导航 timing 预算、以及**渲染开销是否近似线性**（10 倍数据量不应贵 10 倍以上——这条才是真正能抓到 O(n²) 渲染的，绝对预算抓不到）。预算刻意放宽，目的是拦住数量级的劣化，不是卡几毫秒。

## 基线快照（2026-08-26，Apple Silicon 本机回环）

| 场景 | 样本数 | 错误率 | p50 / p95 / p99 (ms) | 吞吐量 |
|---|---|---|---|---|
| 性能（20 线程） | 5,426 | 0% | 1 / 2 / 2 | ~91 req/s（受思考时间限制） |
| 压力（200 线程） | 2,146,989 | 0% | 6 / 36 / 57 | ~11,900 req/s |
| 并发（50×10 集合点） | 1,052 | 0% | 2 / 6 / 7 | tearDown 确认 store 为空 |

压力场景 200 线程下服务端仍未出现 5xx 或超时，拐点在本机配置下尚未到达；要继续探边界可加 `-Jthreads=500 -Jduration=300`。

## 状态约定

- 性能、并发场景自清理（每个 POST 配对 DELETE）；压力场景中断的迭代会留下残余 todo。
- 因此 runner **每类测试都重启 server**，不依赖上一轮清理；手动跑 jmeter 时也建议先重启 `python -m server`。
