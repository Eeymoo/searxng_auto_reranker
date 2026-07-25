# 部署方案（针对现有 s.onemue.cn SearXNG）

> 本方案针对以下现有环境：
> - SearXNG + Valkey 已通过自定义 compose 跑在 `general_net` 网络（静态 IP `10.10.3.6/7`）
> - 反代到 `https://s.onemue.cn/`
> - `settings.yml` 挂载在宿主 `/volume2/docker/searxng/searxng/`
> - 容器使用 `PUID/PGID=999`、`cap_drop: ALL` 的最小权限模式
> - 目标服务器可访问 `192.168.2.79:8080` 的 reranker 服务

## 设计原则

**不动现有的 compose 文件、不动现有容器、不动 settings.yml 之外的任何 NAS 配置。**

新起一个独立的 compose 项目 `auto-reranker`，只跑 PostgreSQL + config-ui 两个容器，并让它们加入已有的 `general_net` 网络。SearXNG 容器只需要：
1. 挂载插件目录（新增一个 volume）
2. `settings.yml` 末尾追加两个配置块
3. 装 Python 依赖（psycopg2 + httpx）

回滚 = 删新目录 + 删 settings.yml 那两个块。

---

## 路径与命名约定

| 项 | 值 |
|---|---|
| 仓库克隆到 | `/volume2/docker/auto-reranker/` |
| 新 compose 项目目录 | `/volume2/docker/auto-reranker/docker/` |
| PG 容器名 | `auto-reranker-postgres` |
| config-ui 容器名 | `auto-reranker-config-ui` |
| 在 `general_net` 中的 IP | `10.10.3.8`（PG）、`10.10.3.9`（config-ui） |
| 现有 searxng 容器名 | `searxng`（保持不变） |
| Token 保存到 | `/volume2/docker/auto-reranker/.token`（chmod 600） |

> IP 选 `.8/.9`，避开你已用的 `.6`（valkey）和 `.7`（searxng）。

---

## 步骤 1：克隆仓库 + 生成 token

SSH 到 NAS，以能写 `/volume2/docker/` 的用户登录（通常是你的主账户，sudo 视情况）：

```bash
cd /volume2/docker
git clone https://github.com/Eeymoo/searxng_auto_reranker.git auto-reranker
cd auto-reranker

# 生成一个强 token 并保存（后续步骤会反复用到）
TOKEN=$(openssl rand -hex 32)
echo "$TOKEN" > /volume2/docker/auto-reranker/.token
chmod 600 /volume2/docker/auto-reranker/.token
echo "保存成功，token 为："
cat /volume2/docker/auto-reranker/.token
echo ""
echo "（请记到密码管理器，后续登录 config-ui、调 API 都需要）"
```

---

## 步骤 2：写本环境专用的 compose 文件

**不要用仓库里的 `docker/docker-compose.yml`**（那是给全新 SearXNG 用的）。这里写一份本环境专用的，放在新位置避免混淆：

```bash
cat > /volume2/docker/auto-reranker/docker/compose.local.yml <<'YAML'
name: auto-reranker

# 复用现有的 general_net 网络，让新容器和 searxng 容器互通
networks:
  general_net:
    external: true

services:
  postgres:
    container_name: auto-reranker-postgres
    image: docker.io/postgres:16-alpine
    restart: unless-stopped
    networks:
      general_net:
        ipv4_address: 10.10.3.8
    environment:
      POSTGRES_USER: auto_reranker
      POSTGRES_PASSWORD: auto_reranker
      POSTGRES_DB: auto_reranker
    volumes:
      - auto-reranker-pg:/var/lib/postgresql/data
      - ../migrations/001_init.sql:/docker-entrypoint-initdb.d/001_init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U auto_reranker"]
      interval: 5s
      timeout: 3s
      retries: 10
    logging:
      driver: "json-file"
      options:
        max-size: "1m"
        max-file: "1"

  config-ui:
    container_name: auto-reranker-config-ui
    build:
      context: ../config-ui
      dockerfile: ../docker/config-ui.Dockerfile
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      general_net:
        ipv4_address: 10.10.3.9
    environment:
      DATABASE_URL: postgresql://auto_reranker:auto_reranker@auto-reranker-postgres:5432/auto_reranker
      AUTORERANKER_TOKEN_FILE: /run/secrets/token
    secrets:
      - token
    # 如果你的反代把 config-ui 也暴露成 https://r.onemue.cn/，就不需要下面的端口
    # 想先内网访问调试，取消下面两行注释
    # ports:
    #   - "3000:3000"
    logging:
      driver: "json-file"
      options:
        max-size: "1m"
        max-file: "1"

volumes:
  auto-reranker-pg:

secrets:
  token:
    file: /volume2/docker/auto-reranker/.token
YAML
```

要点说明：
- `name: auto-reranker` 让 compose 项目独立，不会和你现有的 searxng 项目混淆
- 用 `secrets` 把 token 注入容器（不会出现在 `environment` 里，更不容易被日志/inspect 泄漏）
- 复用 `general_net`，PG 容器名 `auto-reranker-postgres` 作为 DNS 名供 searxng 访问
- config-ui **不暴露端口**（走反代），如果想先调试再取消注释
- 仿照你现有风格，配 `json-file` 日志限大小

但 config-ui 的代码读的是 `AUTORERANKER_TOKEN` 环境变量，需要适配 `_FILE` 模式。我会在第 6 步前修代码。

---

## 步骤 3：启动 PG + config-ui

```bash
cd /volume2/docker/auto-reranker/docker
docker compose -f compose.local.yml up -d --build

# 等到 PG 健康
docker compose -f compose.local.yml ps
# 期望：auto-reranker-postgres 与 auto-reranker-config-ui 都 Up (healthy)

# 验证 PG schema 已建
docker exec auto-reranker-postgres psql -U auto_reranker -d auto_reranker -c '\dt'
# 期望看到：intents / intent_keywords / rules / config_meta
```

---

## 步骤 4：让 searxng 容器装上 Python 依赖

**重要**：searxng 容器是 `cap_drop: ALL`，pip 装包需要临时放开权限。最稳妥是临时起一个同镜像的 sidecar 容器装到 volume，但更简单的办法是临时 `docker exec` 装到容器内（重启容器会丢，但你的 compose 会持久化 volume，重启不会触发）。

更可靠的方案：**把插件依赖打成镜像层**。在 searxng 镜像之上做一个薄封装：

```bash
mkdir -p /volume2/docker/auto-reranker/docker/searxng-wrap
cat > /volume2/docker/auto-reranker/docker/searxng-wrap/Dockerfile <<'DOCKERFILE'
FROM docker.io/searxng/searxng:latest
# 插件运行时依赖：PG 客户端 + HTTP 客户端
USER root
RUN apk add --no-cache --virtual .build-deps \
      gcc musl-dev python3-dev libffi-dev \
 && pip install --no-cache-dir psycopg2-binary httpx \
 && apk del .build-deps \
 && apk add --no-cache libpq
# searxng 镜像的 ENTRYPOINT/USER 由原镜像继承，不需要在这里设
DOCKERFILE
docker build -t searxng-with-reranker /volume2/docker/auto-reranker/docker/searxng-wrap
```

> 这样做的好处：依赖烧进镜像层，searxng 升级时你只需要重新 build 一次；不动 searxng 容器的运行时权限。
> 缺点：你要把现有 compose 里 searxng 服务的 `image:` 改成 `searxng-with-reranker`（下一步）。

---

## 步骤 5：在你现有的 searxng compose 上叠加（仅 3 处改动）

编辑你现有的 searxng compose 文件（路径你需要确认，常见的是 `/volume2/docker/searxng/docker-compose.yml`）。**只改 `searxng` 服务**，redis 那段一字不动：

```yaml
# ① 改镜像（从 docker.io/searxng/searxng:latest 改成本地封装）
  searxng:
    container_name: searxng
    image: searxng-with-reranker      # ← 唯一改动 ①
    restart: unless-stopped
    networks:
        general_net:
            ipv4_address: 10.10.3.7
    volumes:
      - /volume2/docker/searxng/searxng:/etc/searxng:rw
      # ← 唯一改动 ②：挂载插件目录（只读）
      - /volume2/docker/auto-reranker/searx/plugins/auto_reranker:/usr/local/searxng/searx/plugins/auto_reranker:ro
    environment:
      - PUID=999
      - PGID=999
      - SEARXNG_BASE_URL=https://s.onemue.cn/
      - UWSGI_WORKERS=${SEARXNG_UWSGI_WORKERS:-4}
      - UWSGI_THREADS=${SEARXNG_UWSGI_THREADS:-4}
      - UWSGI_UID=999
      - UWSGI_GID=999
      # ← 唯一改动 ③：让插件能连 PG（用容器名，同 general_net 网络可解析）
      - AUTORERANKER_DATABASE_URL=postgresql://auto_reranker:auto_reranker@auto-reranker-postgres:5432/auto_reranker
    dns:
      - 8.8.8.8
    sysctls:
      - net.ipv6.conf.all.disable_ipv6=1
      - net.ipv6.conf.default.disable_ipv6=1
      - net.ipv6.conf.lo.disable_ipv6=1
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
    logging:
      driver: "json-file"
      options:
        max-size: "1m"
        max-file: "1"
```

**全部改动只有 3 行**：`image:` 一行、`volumes:` 加一行、`environment:` 加一行。

应用：

```bash
cd /volume2/docker/searxng   # 你的 searxng compose 所在目录
docker compose up -d         # 自动重建 searxng 容器（redis 不动）
docker logs searxng --tail 30 2>&1 | grep -iE "auto_reranker|plugin|error"
```

> 因为改了 image，必须 `docker compose up -d`（不是 restart），它会重建容器。Redis 不受影响（你没动它）。

---

## 步骤 6：修改 settings.yml 注册插件

```bash
# 一定要先备份
cp /volume2/docker/searxng/searxng/settings.yml \
   /volume2/docker/searxng/searxng/settings.yml.bak-before-reranker

# 编辑（用你顺手的编辑器）
nano /volume2/docker/searxng/searxng/settings.yml
```

**在文件末尾追加**（不要改任何已有内容）：

```yaml

# ===== Auto Reranker 插件配置（追加块，勿改其他配置）=====

# 注册插件（如果你已有 plugins: 节，就把下面这行加进去；否则用整段）
plugins:
  - searx.plugins.auto_reranker.plugin.AutoRerankerPlugin

# 插件运行参数
auto_reranker:
  # 用容器名访问 PG（同 general_net 网络）
  database_url: postgresql://auto_reranker:auto_reranker@auto-reranker-postgres:5432/auto_reranker
  cache_ttl: 30
  # 向量重排通道（接你的 reranker）
  vector_enabled: true
  vector_base_url: "http://192.168.2.79:8080"
  vector_protocol: "jina"           # 你的 reranker 实测是 jina 协议
  vector_api_key: ""
  vector_top_n: 20
  vector_timeout: 2.0               # 内网，2 秒足够；超时静默降级
```

⚠️ **如果 settings.yml 已经有 `plugins:` 节**（比如已经启用了 `Hostnames`），不要写两个 `plugins:`，而是合并：

```yaml
plugins:
  - searx.plugins.hostnames.HostnamesPlugin            # 你已有的
  - searx.plugins.auto_reranker.plugin.AutoRerankerPlugin   # 新增的
```

保存后重启 searxng：

```bash
docker restart searxng
sleep 3
docker logs searxng --tail 50 2>&1 | grep -iE "auto_reranker|plugin|error|traceback"
```

期望看到加载日志，**不应该**看到 `ModuleNotFoundError` / `OperationalError` / `Traceback`。

---

## 步骤 7：（如使用 secrets）适配 config-ui 读 token 文件

compose.local.yml 用了 `AUTORERANKER_TOKEN_FILE`。config-ui 当前只读 `AUTORERANKER_TOKEN`。最简单的适配：在 Dockerfile 的启动脚本里把文件读出来赋给环境变量。或者**跳过 secrets、直接用 environment**：

如果你不想改代码，把 compose.local.yml 里 config-ui 的 `environment` 改成：

```yaml
  config-ui:
    environment:
      DATABASE_URL: postgresql://auto_reranker:auto_reranker@auto-reranker-postgres:5432/auto_reranker
      AUTORERANKER_TOKEN: "${TOKEN}"   # 从 .env 读，下面建一个
```

然后在 `docker/` 目录建一个 `.env` 文件（compose 自动读）：

```bash
cat > /volume2/docker/auto-reranker/docker/.env <<EOF
TOKEN=$(cat /volume2/docker/auto-reranker/.token)
EOF
chmod 600 /volume2/docker/auto-reranker/docker/.env
```

再 `docker compose -f compose.local.yml up -d config-ui` 即可。`docker compose down` 不会删 `.env`，token 持久化。

---

## 步骤 8：配置 config-ui 的反代（可选）

如果你想通过域名访问 config-ui（比如 `https://r.onemue.cn/`），在 NAS 的反代（Nginx Proxy Manager / Caddy / Synology 反代）加一条：

```
r.onemue.cn -> 10.10.3.9:3000
```

否则直接用 `http://<NAS的局域网IP>:3000`。注意需要在 compose.local.yml 取消注释 `ports: - "3000:3000"` 才行。

---

## 步骤 9：灌入种子规则并端到端验证

```bash
# 灌种子（3 意图 / 13 关键词 / 12 规则，含游戏/新闻/法条/黑名单）
docker exec -i auto-reranker-postgres \
  psql -U auto_reranker -d auto_reranker \
  < /volume2/docker/auto-reranker/migrations/002_seed_e2e.sql

# 验证 1：通过 searxng 搜一个查询
curl -s "https://s.onemue.cn/search?q=今天热点新闻&format=json" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f\"{r.get('score',0):>5}  {r.get('url')}\") for r in d['results'][:8]]"
# 期望：微博热搜/政府新闻在前，Walmart 类沉底

# 验证 2：通过 config-ui API 测一个 URL 命中什么规则
TOKEN=$(cat /volume2/docker/auto-reranker/.token)
curl -s -X POST http://10.10.3.9:3000/api/test \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"url":"https://store.steampowered.com/app/1091500","query":"购买 赛博朋克2077 游戏"}' \
  | python3 -m json.tool
# 期望 coefficient=5（Steam 规则命中，gaming 意图命中）
```

---

## 常见坑（针对本环境）

| 症状 | 原因 | 解决 |
|---|---|---|
| searxng 日志报 `ModuleNotFoundError: psycopg2` | 镜像没重建 | `docker compose up -d` 而非 restart；确认 image 改成了 `searxng-with-reranker` |
| searxng 日志报 `PG unavailable` | searxng 容器连不到 PG | 确认两边都在 `general_net`；从 searxng 容器测：`docker exec searxng ping auto-reranker-postgres` |
| searxng 日志报 `permission denied` 读插件目录 | 插件目录权限 | `chmod -R a+r /volume2/docker/auto-reranker/searx/plugins/auto_reranker` |
| config-ui 401 | token 不匹配 | 对比 `.env` / `.token` 内容 |
| 向量重排无效果 | reranker 不可达或协议错 | 在 searxng 容器内：`docker exec searxng wget -qO- --post-data='{"query":"test","texts":["a"]}' --header='Content-Type: application/json' http://192.168.2.79:8080/rerank` |
| SearXNG 反代报 502 | searxng 容器没起来 | `docker logs searxng --tail 100`，通常是 settings.yml 语法错误，用 `.bak-before-reranker` 恢复 |

---

## 一键回滚

```bash
# 1. 恢复 settings.yml
cp /volume2/docker/searxng/searxng/settings.yml.bak-before-reranker \
   /volume2/docker/searxng/searxng/settings.yml

# 2. 把 searxng compose 的 image 改回 docker.io/searxng/searxng:latest，
#    删掉新增的 volume 和 environment 行，docker compose up -d

# 3. 停掉 PG + config-ui（数据保留，下次还能用）
cd /volume2/docker/auto-reranker/docker
docker compose -f compose.local.yml down

# 4. （可选）彻底删除数据和目录
# docker compose -f compose.local.yml down -v
# rm -rf /volume2/docker/auto-reranker
```

你的 SearXNG 现有引擎配置、主题、Redis 数据**完全不受影响**。
