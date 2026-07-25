# 叠加部署指南：已有 SearXNG 容器 + 新 PG + config-ui

> 适用场景：你已经用 Docker 跑着一个 SearXNG 实例（有自己调好的 `settings.yml` / 引擎权重 / 主题），现在只想把 **Auto Reranker 插件**叠加进去，不替换、不重启现有 SearXNG 之外的基础设施。
>
> 目标服务器能访问 `192.168.2.79:8080` 的 reranker 服务。

## 整体思路

```
┌─────────────────────────────────────────┐
│  你的服务器                              │
│                                          │
│  ┌───────────────┐    ┌──────────────┐  │
│  │  现有 searxng  │    │  新 PG 容器   │  │
│  │  容器 (不动)   │◀──│ auto_reranker│  │
│  │  + 挂载插件    │    │  数据库      │  │
│  └───────────────┘    └──────┬───────┘  │
│         ▲                     │          │
│         │                     │          │
│       挂载 settings.yml      读写        │
│         │                     │          │
│  ┌──────┴──────┐       ┌──────▼───────┐  │
│  │ /opt/auto-  │       │ config-ui    │  │
│  │ reranker/   │       │ 容器 (新)    │  │
│  │ searx/      │       │ :3000        │  │
│  │  plugins/   │       └──────────────┘  │
│  └─────────────┘                         │
└─────────────────────────────────────────┘
        │
        │ HTTP rerank (可选)
        ▼
   192.168.2.79:8080 (你现有的 reranker)
```

三件事:
1. **PG + config-ui 用新容器** (本仓库的 docker-compose 提供)
2. **现有 SearXNG 容器加两个 volume 挂载** + 装 Python 依赖 (需要重启一次容器)
3. **reranker 地址**写 `http://192.168.2.79:8080`,协议 `jina`

---

## 步骤 1：在目标服务器准备插件目录

```bash
# 1.1 克隆仓库到服务器（任意目录，举例用 /opt）
sudo mkdir -p /opt/auto-reranker
sudo chown $USER:$USER /opt/auto-reranker
cd /opt/auto-reranker
git clone https://github.com/Eeymoo/searxng_auto_reranker.git .

# 1.2 生成一个强 token（记住它，下面两处都要用）
TOKEN=$(openssl rand -hex 32)
echo "你的 token: $TOKEN"
# 把它记到密码管理器里，下一步要用
```

---

## 步骤 2：起 PG + config-ui 容器

仓库里的 `docker/docker-compose.yml` 已经定义了这两个服务（外加 SearXNG，但你**不需要**它，下面会改）。

```bash
cd /opt/auto-reranker/searxng_auto_reranker/docker

# 2.1 把 compose 里多余的 searxng 服务注释掉（你已有自己的）
#     或者用 --scale searxng=0 跳过它
#     推荐用下面的 override 文件（步骤 2.2）

# 2.2 写一个 compose override，禁用仓库里的 searxng 服务、注入 token
cat > docker-compose.override.yml <<EOF
services:
  searxng:
    profiles: ["unused"]          # 这样它不会启动
  config-ui:
    environment:
      AUTORERANKER_TOKEN: "$TOKEN"
EOF

# 2.3 启动
docker compose up -d postgres config-ui

# 2.4 等待并验证
docker compose ps
# 期望看到 postgres 和 config-ui 都 Up，searxng 不在列

# 2.5 验证 config-ui 能登录（用刚才的 token）
curl -s -X POST http://localhost:3000/api/login \
  -H "Content-Type: application/json" \
  -d "{\"token\":\"$TOKEN\"}" -i | grep -i "set-cookie"
# 期望: set-cookie: auto_reranker_token=...; HttpOnly
```

PG 自动跑了 `001_init.sql`（建表），config-ui 起在 `:3000`。

---

## 步骤 3：把插件挂进你现有的 SearXNG 容器

### 3.1 找到你现有 searxng 容器的名字和挂载点

```bash
docker ps --filter "ancestor=searxng/searxng" --format "{{.Names}}\t{{.Image}}"
# 比如输出: my-searxng  searxng/searxng:latest

# 看它现在挂载了哪些 volume（找到 settings.yml 的宿主路径）
docker inspect my-searxng --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
# 比如输出: /srv/searxng/settings.yml -> /etc/searxng/settings.yml
```

记下：
- 容器名（例：`my-searxng`）
- 宿主上的 `settings.yml` 路径（例：`/srv/searxng/settings.yml`）

### 3.2 给现有容器加两个 volume（需要重建容器）

如果你用的是 `docker run`，重建时追加：
```bash
docker stop my-searxng && docker rm my-searxng

# 在你原来的 docker run 命令末尾追加这两行：
#   -v /opt/auto-reranker/searxng_auto_reranker/searx/plugins/auto_reranker:/usr/local/searxng/searx/plugins/auto_reranker:ro \
#   --network auto-reranker_default \      # 让它能连到 PG 容器
#   -e AUTORERANKER_DATABASE_URL=postgresql://auto_reranker:auto_reranker@postgres:5432/auto_reranker \
```

如果你用的是 `docker-compose.yml`（**推荐**），在你现有的 compose 文件里给 searxng service 加：
```yaml
services:
  your-searxng:                      # 你原本的 service 名
    # ... 你原本的所有配置不动 ...
    volumes:
      - /your/origin/settings.yml:/etc/searxng/settings.yml:ro
      - /opt/auto-reranker/searxng_auto_reranker/searx/plugins/auto_reranker:/usr/local/searxng/searx/plugins/auto_reranker:ro   # ← 加这行
    networks:
      - default
      - auto-reranker_default        # ← 加这行,让它能连 PG
    environment:
      AUTORERANKER_DATABASE_URL: postgresql://auto_reranker:auto_reranker@postgres:5432/auto_reranker  # ← 加这行

networks:
  auto-reranker_default:
    external: true
```

### 3.3 安装插件的 Python 依赖（关键，否则插件加载时报 ModuleNotFoundError）

```bash
# 进容器装 psycopg2 + httpx
docker exec -u root -it my-searxng sh -c '
  pip install --no-cache-dir psycopg2-binary httpx
'
# 注意：searxng/searxng 镜像内 Python 是系统 Python，pip 即可用
# 如果你的镜像基于 Alpine 且没装 gcc，可能需要先 apk add gcc musl-dev python3-dev libffi-dev
```

### 3.4 修改 settings.yml 注册插件（只加两个块）

```bash
# 备份
cp /srv/searxng/settings.yml /srv/searxng/settings.yml.bak

# 编辑
nano /srv/searxng/settings.yml
```

在你**现有的** `settings.yml` 里加这两个块（其他配置一行都不要改）：

```yaml
# 在顶层（与 server:、engine: 等同级）追加 plugins 块；
# 如果你已经有 plugins: 节，就在下面追加一行
plugins:
  - searx.plugins.auto_reranker.plugin.AutoRerankerPlugin

# 顶层追加 auto_reranker 配置节
auto_reranker:
  # 指向刚才起的 PG 容器（容器名 postgres，由 auto-reranker_default 网络解析）
  database_url: postgresql://auto_reranker:auto_reranker@postgres:5432/auto_reranker
  cache_ttl: 30

  # 向量重排通道（接 192.168.2.79:8080）
  vector_enabled: true
  vector_base_url: "http://192.168.2.79:8080"
  vector_protocol: "jina"             # 你的 reranker 实测是 jina 协议
  vector_api_key: ""                  # 内网无 key,留空
  vector_top_n: 20
  vector_timeout: 2.0                 # 给 2 秒,内网足够;超时静默降级
```

⚠️ **如果你的 `plugins:` 已经有别的插件**（比如 `Hash_filter`、`Hostnames`），不要覆盖，**追加一行**即可：
```yaml
plugins:
  - searx.plugins.hostnames.HostnamesPlugin     # 你已有的
  - searx.plugins.auto_reranker.plugin.AutoRerankerPlugin  # ← 新增
```

### 3.5 重启 SearXNG 让配置生效

```bash
docker restart my-searxng

# 查看日志确认插件加载成功
docker logs my-searxng --tail 50 2>&1 | grep -i "auto_reranker\|plugin\|error"
# 期望看到：
#   INFO   searx.plugins ... loading 'searx.plugins.auto_reranker.plugin.AutoRerankerPlugin'
# 不应该看到：ModuleNotFoundError、OperationalError、Traceback
```

---

## 步骤 4：灌入初始规则并验证

### 4.1 通过 config-ui 灌规则（推荐，有 UI）

浏览器打开 `http://<服务器IP>:3000/login`，用步骤 1.2 的 token 登录。

参考 [`docs/CONFIG_GUIDE.md`](docs/CONFIG_GUIDE.md) 的「典型中文场景规则示例」加规则：
- 政府/官媒加权（`.*\.gov\.cn/.*` 系数 3.0 等）
- 游戏意图 → Steam 加权（关键词「游戏/购买/steam」+ 规则 `.*steampowered\.com/.*` 系数 5.0）
- 内容农场黑名单（系数 0）

加完点页面右上角 **Refresh now** 按钮，插件下次搜索立即生效（绕 TTL）。

### 4.2 直接灌种子（懒人方案）

```bash
docker exec -i auto-reranker-postgres-1 \
  psql -U auto_reranker auto_reranker \
  < /opt/auto-reranker/searxng_auto_reranker/migrations/002_seed_e2e.sql
```

这会灌入 3 意图 / 13 关键词 / 12 规则（含游戏/新闻/法条/黑名单），与之前实测的那套一致。

### 4.3 端到端验证

```bash
# 搜一个中文查询，看结果是否改善
curl -s "http://localhost:8080/search?q=今天热点新闻&format=json" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f\"{r.get('score',0):.2f}  {r.get('url')}\") for r in d['results'][:5]]"
# 期望：微博热搜/政府新闻在前，Walmart 类沉底

# 用 /api/test 看某个 URL 会命中什么规则
curl -s -X POST http://localhost:3000/api/test \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"url":"https://store.steampowered.com/app/1091500","query":"购买 游戏"}' | python3 -m json.tool
# 期望 coefficient: 5（Steam 规则命中，gaming 意图命中）
```

---

## 常见坑

| 症状 | 原因 | 解决 |
|------|------|------|
| 插件日志报 `ModuleNotFoundError: psycopg2` | 容器内没装 Python 依赖 | 步骤 3.3 重做 |
| 插件日志报 `PG unavailable` | searxng 容器连不到 `postgres` 主机名 | 没加 `auto-reranker_default` 网络，回到 3.2 |
| `/api/refresh` 点了无效 | 之前版本的 bug | 确认仓库版本 ≥ 当前提交 `8700f13`（B1 已修） |
| 向量重排没效果 | reranker 不可达或协议写错 | `docker exec my-searxng curl -X POST http://192.168.2.79:8080/rerank -H 'Content-Type: application/json' -d '{"query":"test","texts":["a"],"top_n":1}'` 测试 |
| config-ui 401 | token 不匹配 | 确认容器 env 里的 token 和登录用的一致 |
| 现有 SearXNG 配置丢失 | 误覆盖了 settings.yml | 用 3.4 的备份 `settings.yml.bak` 恢复 |

---

## 一次性回滚

插件是纯叠加，回滚只需：
1. `settings.yml` 里删掉 `plugins:` 的 AutoRerankerPlugin 行 + `auto_reranker:` 整节
2. `docker restart my-searxng`
3. （可选）`docker compose down`（在 `/opt/auto-reranker/.../docker/`）停掉 PG + config-ui

你的 SearXNG 数据、引擎配置、主题、Redis 全部不受影响。
