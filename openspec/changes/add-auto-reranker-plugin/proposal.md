## Why

SearXNG 在中文查询场景下相关性严重不足：搜「今天热点新闻」返回墨西哥 Walmart 门店信息，搜「微博热搜」返回 Wikipedia 英文页面。根因是默认启用的引擎对中文支持差、所有引擎权重相同导致中文友好源（Bing、ChinaSo 等）被稀释，而现有的 Hostnames 插件只能无条件屏蔽/降权域名，无法按查询意图动态调整站点权威度，也缺乏基于语义的向量重排能力。需要一个完全兼容 SearXNG 插件体系、可可视化配置的二次重排层，在不重写原生排名（引擎原始得分 × 权重 × 可靠性）的前提下叠加规则与向量排序。

## What Changes

- 新增 SearXNG 插件 `Auto Reranker`，通过 `settings.yml` 的 `plugins:` 配置注册，实现官方 `post_search` 钩子对聚合结果进行二次重排
- 新增规则重排通道：支持按 URL 正则匹配对结果进行权重系数调整（如政府官网加权、Steam 商店对游戏查询加权），权重为 0 的结果直接剔除
- 新增向量重排通道：可开关调用外部 Reranker/Embedding 服务，对 Top N（默认 20~25）结果按查询语义相关性重新打分
- 新增配置持久化层：使用 PostgreSQL 存储重排规则、权重系数、黑名单、意图关键词，支持热更新（无需重启 SearXNG）
- 新增 Web 配置系统（Bun.js + Next.js + shadcn/ui）：通过静态 Token 准入，提供 URL 正则规则、权重系数、黑名单、意图关键词的 CRUD 页面
- 新增意图路由能力：支持按查询关键词（如「游戏」「编程」「新闻」）动态匹配不同的站点权威度规则集合
- **BREAKING**：无（纯新增插件，不修改 SearXNG 现有功能；启用前不影响任何已有行为）

## Capabilities

### New Capabilities

- `rule-rerank`: 基于 URL 正则规则的二次重排能力，包含权重系数调整、黑名单剔除（权重为 0）、稳定排序
- `vector-rerank`: 基于外部 Reranker/Embedding 服务的语义重排能力，可开关、对 Top N 重打分、失败静默降级
- `intent-routing`: 按查询关键词匹配意图分类，动态选择对应的站点权威度规则集合（如游戏→Steam、编程→官方文档）
- `config-store`: 配置持久化与热更新能力，基于 PostgreSQL 存储，运行时读取，免重启生效
- `config-admin-ui`: 极简 Web 配置系统，静态 Token 准入，提供规则/权重/黑名单/意图关键词的 CRUD 管理界面

### Modified Capabilities

<!-- 无已有 capability 被修改，本项目为全新仓库，openspec/specs/ 为空 -->

## Impact

- **新增代码**：
  - Python 插件目录 `searx/plugins/auto_reranker/`（`__init__.py`、`plugin.py`、`rule_engine.py`、`vector_engine.py`、`intent_router.py`、`config_loader.py`、`pg_client.py`）
  - Web 配置系统目录 `config-ui/`（Next.js app router、shadcn/ui 组件、API routes）
  - 数据库迁移 `migrations/`（PostgreSQL schema：规则表、意图表、黑名单表、配置元数据表）
- **外部依赖**：
  - Python：`psycopg2` 或 `SQLAlchemy`（PG 客户端）、`httpx` 或 `requests`（调用向量服务）
  - Web：Bun.js 运行时、Next.js、shadcn/ui、`pg` 或 Prisma（Node PG 客户端）
  - 可选外部服务：Reranker/Embedding HTTP 服务（兼容 Cohere/Jina/BGE 等通用接口约定）
- **SearXNG 集成点**：`settings.yml` 的 `plugins:` 字段追加全限定类名，新增 `auto_reranker` 配置节（PG 连接串、向量服务地址、Top N、超时、开关）
- **部署形态**：插件文件挂载进 SearXNG 容器；配置系统独立部署（可同机或分容器）；PostgreSQL 可复用已有实例或新建
- **性能影响**：规则层毫秒级（正则匹配）；向量层对 Top 20~25 控制在 100~500ms 内，失败时静默降级回原排序，不阻塞主流程
