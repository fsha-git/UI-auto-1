# 容器化测试环境

在 macOS、Linux、Windows 上用**同一条命令**跑完这个仓库的全部四类检查，不需要在
宿主机装 Python、Playwright、浏览器、JDK 或 JMeter，只需要 Docker。

```bash
docker compose run --rm all
```

一次跑完 pytest 全量套件 → 变异检测回归 → 约定审计 → JMeter 七类压测，中途失败不
停，最后汇总失败清单。对应 [`AGENTS.md`](AGENTS.md) Verification 的第 1、2、3、4 步。

---

## 前置条件

| 平台 | 需要 | 备注 |
|---|---|---|
| macOS | Docker Desktop 4.x+ | Apple Silicon 原生跑 arm64 镜像，不走 Rosetta |
| Linux | Docker Engine 24+ 与 Compose v2 | 见下面的 [文件属主](#linux-文件属主) |
| Windows | Docker Desktop + WSL2 后端 | 仓库请放在 **WSL2 文件系统内**（如 `\\wsl$\Ubuntu\home\you\UI_auto_1`），放在 `C:\` 下绑定挂载要跨 9p，测试会慢好几倍 |

命令在 PowerShell、cmd、bash、zsh 里写法完全一致。

---

## 四个 service

| 命令 | 做什么 | 镜像 | 大致耗时 |
|---|---|---|---|
| `docker compose run --rm tests` | 全量 pytest（含 Python 覆盖率与前端 JS 染色报告） | `test` | 几分钟 |
| `docker compose run --rm triage` | 对 30 个变异体逐一跑对应测试，与 `TRIAGE.md` 比对 | `test` | 十几分钟 |
| `docker compose run --rm tests audit` | `AGENTS.md` 的四条约定 grep | `test` | 秒级 |
| `docker compose run --rm perf` | JMeter 六类压测（`soak` 默认不含在内） | `perf` | 十几分钟 |
| `docker compose run --rm all` | 上面四项全部 | `perf` | 半小时起 |

两个镜像：`test`（Python + Chromium，约 1.6 GB）和 `perf`（在它之上再加 JDK 21 +
JMeter，约 +400 MB）。只跑 pytest 的人不需要拉 `perf`。

### 传参

首个参数认不出是任务名或可执行文件时，整串参数会交给该 service 的默认任务，所以
可以直接写平时那套：

```bash
docker compose run --rm tests tests/test_chart.py -v
docker compose run --rm tests -k "checkbox"
docker compose run --rm tests --demo-html web/bugs/bug_add_dedupes_items.html
docker compose run --rm perf performance -Jduration=15 -Jrampup=3
```

也可以显式点名任务（`pytest` / `triage` / `audit` / `perf` / `all`），或者拿一个真
实命令当逃生口：

```bash
docker compose run --rm tests audit
docker compose run --rm tests bash          # 进容器手动排查
```

`PYTEST_ARGS` 是给固定参数用的，带引号的参数会保留成一个词：

```bash
PYTEST_ARGS='-m "not perf"' docker compose run --rm tests
```

---

## 报告落在哪

仓库整个绑定挂载进容器的 `/work`，所以产物直接写回宿主机，路径与本机原生跑时完全
一样（都已 gitignore）：

| 产物 | 路径 |
|---|---|
| trace / 失败截图 / 视频 | `test-results/<用例目录>/` |
| Python 覆盖率 | `reports/coverage-py/index.html` |
| 前端 JS 染色 | `reports/coverage-js/index.html` |
| JMeter 各场景 dashboard | `reports/jmeter/<类型>/dashboard/index.html` |
| JMeter 跨运行趋势 | `reports/jmeter/perf_dashboard.html` |

`playwright show-trace` 是 GUI 程序，容器里跑不了 —— 在**宿主机**上看：

```bash
playwright show-trace test-results/<用例目录>/trace.zip
```

---

## Linux 文件属主

容器默认以 root 跑。macOS 和 Windows 的 Docker Desktop 会替你处理绑定挂载的属主，
**Linux 宿主机不会** —— 不管的话 `reports/`、`test-results/`、`.auth/` 里会留下 root
属主的文件。传自己的 UID/GID：

```bash
HOST_UID=$(id -u) HOST_GID=$(id -g) docker compose run --rm all
```

嫌每次都写就落到 `.env`（compose 会自动读，已 gitignore）：

```bash
printf 'HOST_UID=%s\nHOST_GID=%s\n' "$(id -u)" "$(id -g)" > .env
```

忘了传的话，容器启动时的预检会直接告诉你 `/work` 不可写，而不是等测试跑到一半才炸
出一个不相干的错。其余可配置项见 [`.env.example`](.env.example)。

---

## CI

[`.github/workflows/tests.yml`](.github/workflows/tests.yml) 用的是与上面**逐字相
同**的 compose 命令，CI 与本地不会分叉：任何在 CI 上出现的失败，本机换成同一条命令
就能重现。

- `test` job：每次 push / PR 跑 pytest + triage + audit，产物上传成 `reports` artifact。
- `perf` job：只在手动触发（workflow_dispatch）和每周定时跑，且目前是
  `continue-on-error: true` —— 见下面的取舍第 4 条。

镜像用 buildx 的 GitHub Actions 缓存（`type=gha`）；没有它每次都要重拉 1.4 GB 基础
镜像并重装依赖。

---

## 已知取舍

1. **前端性能护栏是墙钟时间断言。** `tests/test_frontend_perf.py` 断的是 3000 ms
   渲染 / 2000 ms DCL / 3000 ms 弹窗。容器被 CPU 限流时它是第一个失败的。默认仍然
   跑（它属于「所有测试」），迭代时的逃生口是
   `PYTEST_ARGS='-m "not perf"' docker compose run --rm tests`。
   Docker Desktop 里给足 CPU（建议 ≥4 核）能显著降低误报。
2. **`--reruns 2` 会掩盖抖动。** `pytest.ini` 里配了重试，而 `AGENTS.md` 要求「零
   rerun，不只是零失败」。容器里的抖动会以 rerun 计数的形式暴露出来，判定标准仍以
   `AGENTS.md` 为准。
3. **`triage` 慢是设计使然。** 30 个变异体各要一次嵌套 pytest，每次都冷启动浏览器。
4. **压测阈值是在开发机上定的。** `--max-p95 800 --min-throughput 50` 这些绝对值没
   有 GitHub runner 上的基线，所以 CI 的 perf job 先设成不阻塞，攒几轮
   `reports/jmeter/history.jsonl` 数据、确认阈值合理之后再收紧。
5. **Chromium 需要大的 `/dev/shm`。** compose 里已经设了 `shm_size: 1gb`；不经
   compose 直接 `docker run` 时记得自己带 `--shm-size=1g`，否则会遇到看起来像
   flaky 的随机崩溃。

---

## Studio 不在 compose 里

低代码可视化测试页面（[`STUDIO.md`](STUDIO.md)）**刻意没有做成 compose service**。
`studio/__main__.py` 会拒绝绑定非环回地址，除非显式传 `--i-know` —— 因为该进程按
HTTP 请求执行 pytest，暴露到网络上等于交出远程代码执行。要用 Studio 就在宿主机按
`STUDIO.md` 的原生方式跑：

```bash
python -m studio --port 8100
```

同理，`python -m server --port 8000`（给 `playwright codegen` 用的固定端口 demo
站点）也留在宿主机。容器里跑 pytest 时根本不需要它们：`tests/conftest.py` 的
`demo_server` fixture 会在进程内起一个随机端口的服务，容器不需要暴露任何端口。

---

## 镜像版本

`docker/Dockerfile` 的基础镜像 tag `v1.62.0` 必须与 `requirements.txt` 里的
`playwright==1.62.0` 保持一致 —— 镜像自带的浏览器构建是按 Playwright 版本编号的，
两边漂开，pip 装的 Playwright 会去找镜像里不存在的目录。**升级 Playwright 时同时
改这两处。**

JMeter 版本由 `JMETER_VERSION` build arg 控制（默认 5.6.3），校验和默认从 Apache
的 `.sha512` 边车文件取。想要钉死摘要（挡住上游被换包，而不只是传输损坏）：

```bash
docker compose build --build-arg JMETER_SHA512=<128位十六进制> perf
```
