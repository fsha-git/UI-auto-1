# JMeter 性能 / 压力 / 并发测试

用 JMeter 对 `server/app.py` 的 `/api/*` 接口做三类非功能测试：性能（基准负载）、压力（递增负载找拐点）、并发（集合点验证 `todo_store` 锁的正确性）。

## 前置条件

```bash
brew install jmeter   # 依赖的 openjdk 已随 Homebrew 提供
```

无需手动配置 JAVA_HOME：`perf/run_perf.sh` 在未设置时会自动指向 `/opt/homebrew/opt/openjdk@21`。

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
perf/run_perf.sh all            # 依次跑三类
perf/run_perf.sh performance    # 只跑某一类
```

脚本会：检查 jmeter → **每类测试启动全新 server 进程**（保证 `todo_store` 为空、id 从 1 开始）→ `jmeter -n` 无 GUI 运行 → 生成 HTML dashboard → 用 `perf/check_jtl.py` 做阈值校验 → kill server。任一类失败则退出码非零。

额外参数直接透传给 jmeter，可覆盖 JMX 中的默认值：

```bash
perf/run_perf.sh stress -Jthreads=300 -Jduration=300
```

```bash
perf/run_perf.sh concurrency -Jthreads=100 -Jrendezvous=100 -Jloops=20
```

端口冲突时用 `PERF_PORT=8001 perf/run_perf.sh all` 换端口。

## 三个测试场景

| 场景 | JMX | 默认参数 | 流程 | 通过标准 |
|---|---|---|---|---|
| 性能（基准负载） | `perf/performance.jmx` | threads=20, rampup=10s, duration=60s，思考时间 100–300ms | 登录一次 → 循环 health / stats / 查 todos / 建 todo(201) / 删 todo(204) | 错误率 ≤1%，p95 ≤800ms |
| 压力（递增负载） | `perf/stress.jmx` | threads=200, rampup=120s, duration=180s，无思考时间 | 同上（最大压力） | 错误率 ≤10%，5xx =0；延迟仅作观察 |
| 并发（集合点） | `perf/concurrency.jmx` | threads=50, rendezvous=50, loops=10, rampup=2s | POST 和 DELETE 各挂 SyncTimer，50 线程同时发起；tearDown 校验最终 todos 为空 | 错误率 =0，5xx =0，结束时 store 为空 |

所有场景公共部分：`OnceOnlyController` 登录一次提取 token，线程组级 HeaderManager 注入 `Authorization: Bearer ${token}`，每个请求都断言响应码。登录失败的线程会被 Result Status Action Handler 直接终止 —— 否则该线程终身没有 token，后续每次迭代都产生 401，把真实错误率放大几个数量级（首轮压测中 126 个登录失败级联出了 11 万个 401）。

并发场景的 rampup=2s 是刻意的：集合点由 SyncTimer 保证（线程在集合点等齐后同时发请求），建连可以平缓进行，避免把"同时建连打爆 backlog"误报成锁的问题。

### 各场景设计意图

- **性能**：带思考时间模拟 20 个真实用户的混合读写流量，从 dashboard 读吞吐量和 p50/p95/p99 延迟作为基线。POST 与 DELETE 配对，测试自清理。
- **压力**：120 秒线性加压到 200 线程再保持 60 秒，无思考时间。在 dashboard 的 Response Times Over Time / Codes per Second 图上找性能拐点（`ThreadingHTTPServer` 每连接一线程，本身就是被测瓶颈）。
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
