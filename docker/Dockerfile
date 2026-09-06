# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# test —— 跑 pytest / triage / audit 需要的一切
#
# 基础镜像自带 Chromium、它的全部系统依赖，以及 Playwright 打包的 ffmpeg
# （pytest.ini 的 --video=retain-on-failure 需要它）。浏览器已经在
# /ms-playwright，PLAYWRIGHT_BROWSERS_PATH 也由基础镜像设好，所以这里
# 不需要再跑 `playwright install`。
#
# !! tag 里的 v1.62.0 必须与 requirements.txt 里的 playwright==1.62.0 一致 !!
# 两边漂开，pip 装的 Playwright 会去找镜像里不存在的浏览器构建目录。
# noble tag 同时有 amd64 与 arm64 manifest，Apple Silicon 上原生跑，不走 Rosetta。
# ---------------------------------------------------------------------------
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble AS test

# HOME=/tmp 的原因：docker-compose 的 user: 可能把容器跑成宿主机的任意 UID
# （Linux 上用来避免在 reports/ 留下 root 属主的文件）。那个 UID 在 /etc/passwd
# 里没有条目，HOME 会解析成 /，不可写；Playwright 和 pip 都需要一个能写的 HOME。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp

WORKDIR /work

# 依赖层放在源码层之上：改代码不会触发重新装依赖。
COPY requirements.txt /work/requirements.txt
RUN pip install --no-cache-dir -r /work/requirements.txt

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# 把源码也烤进镜像，这样不挂载卷也能跑（`docker run <image> pytest`）。
# 本地和 CI 都会用绑定挂载把这份副本盖掉，好让报告直接落到宿主机。
COPY . /work

# entrypoint.sh 在没给任务名时跑 $DEFAULT_TASK，并把认不出来的首个参数
# 当作该任务的参数（见脚本头部注释）。perf target 会把它改成 perf。
ENV DEFAULT_TASK=pytest

ENTRYPOINT ["entrypoint.sh"]
CMD ["pytest"]


# ---------------------------------------------------------------------------
# perf —— 在 test 之上再加 JMeter 七类压测需要的 Java / JMeter / 系统工具
#
# 单独一个 target 而不是塞进 test：JDK + JMeter 是 +400MB，日常只跑 pytest
# 的人不该为此付出拉取代价。
# ---------------------------------------------------------------------------
FROM test AS perf

ARG JMETER_VERSION=5.6.3

# 留空时回落到从同一目录下载 .sha512 边车文件校验（挡得住传输损坏，挡不住上游
# 被换包）。想要更强的保证就在 build 时传入钉死的摘要：
#   docker compose build --build-arg JMETER_SHA512=<128位十六进制> perf
ARG JMETER_SHA512=

USER root

# lsof 给 run_perf.sh 的端口占用检查用，curl 给它的 server 健康探测用。
# /opt/java 软链是为了有个不含 arch 的稳定 JAVA_HOME（amd64/arm64 目录名不同）。
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        openjdk-21-jre-headless \
        lsof \
        curl \
        ca-certificates \
        procps; \
    rm -rf /var/lib/apt/lists/*; \
    ln -s "$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")" /opt/java

ENV JAVA_HOME=/opt/java

# 校验和比对刻意不用 `sha512sum -c`：Apache 各版本的 .sha512 有两种格式
# （coreutils 的 "<hex>  <file>" 和 gpg --print-md 的 "<file>: AB CD ..."），
# 去掉全部空白后做子串比对对两种格式都成立。
RUN set -eux; \
    base="https://archive.apache.org/dist/jmeter/binaries"; \
    tgz="apache-jmeter-${JMETER_VERSION}.tgz"; \
    curl -fsSL -o "/tmp/${tgz}" "${base}/${tgz}"; \
    actual="$(sha512sum "/tmp/${tgz}" | cut -d' ' -f1)"; \
    if [ -n "${JMETER_SHA512}" ]; then \
        expected="$(printf '%s' "${JMETER_SHA512}" | tr 'A-Z' 'a-z')"; \
    else \
        curl -fsSL -o "/tmp/${tgz}.sha512" "${base}/${tgz}.sha512"; \
        expected="$(tr -d '[:space:]' < "/tmp/${tgz}.sha512" | tr 'A-Z' 'a-z')"; \
    fi; \
    case "${expected}" in \
        *"${actual}"*) echo "jmeter checksum ok: ${actual}" ;; \
        *) echo "jmeter checksum MISMATCH: got ${actual}" >&2; exit 1 ;; \
    esac; \
    mkdir -p /opt/jmeter; \
    tar -xzf "/tmp/${tgz}" -C /opt/jmeter --strip-components=1; \
    rm -f "/tmp/${tgz}" "/tmp/${tgz}.sha512"

ENV PATH=/opt/jmeter/bin:$PATH

RUN jmeter --version

ENV DEFAULT_TASK=perf

CMD ["perf"]
