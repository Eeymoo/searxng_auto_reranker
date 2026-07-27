## Context

SearXNG 的原生排名基于「引擎原始得分 × (weight × 可靠性系数)」，聚合多引擎结果后输出。该机制在英文查询下表现良好，但在中文场景存在系统性偏差：默认启用的引擎对中文支持差（如 Google 对中文新闻热点召回弱）、所有引擎权重相同导致中文友好源（Bing、ChinaSo、微博）被稀释、Hostnames 插件只能无条件域名屏蔽无法按查询意图动态调整。

现有补救手段（手动调引擎权重、Hostnames 插件）存在三个核心缺陷：无法按查询意图路由（游戏应优先 Steam、编程应优先官方文档）、无语义相关性判断（仅靠域名）、配置变更需重启或依赖文件挂载。

本设计在不重写 SearXNG 前端、不引入 LLM 在线打分的前提下，叠加一个可配置的二次重排层，通过「规则 + 向量」双通道弥补原生排名在中文场景的不足。

**约束**：
- 必须使用官方 `Plugin` 基类与 `post_search` 钩子，通过 `settings.yml` 的 `plugins:` 注册
- 插件语言为 Python（与 SearXNG 一致）
- 配置系统技术栈固定：Bun.js + Next.js + shadcn/ui
- 数据库固定：PostgreSQL
- 不引入 LLM 在线打分，仅支持向量/Reranker 模型

**利益相关方**：自托管 SearXNG 实例的运维者（个人/小团队）、最终用户（中文搜索者）。

## Goals / Non-Goals

**Goals:**
- 提供完全兼容 SearXNG 插件体系的 `Auto Reranker` 插件，通过 `post_search` 钩子对聚合结果二次重排
- 支持规则重排：URL 正则匹配 + 权重系数调整 + 权重为 0 剔除
- 支持向量重排：可开关调用外部 Reranker 服务，对 Top N 重打分，失败静默降级
- 支持意图路由：按查询关键词动态选择规则集合
- 配置持久化于 PostgreSQL，支持热更新（免重启 SearXNG）
- 提供极简 Web 配置系统（静态 Token 准入），覆盖规则/权重/黑名单/意图关键词 CRUD
- 性能可控：规则层毫秒级；向量层 Top 20~25 在 100~500ms 内

**Non-Goals:**
- 不实现复杂登录/权限系统（仅静态 Token 准入，无多用户/角色）
- 不重写 SearXNG 前端页面或主题（仅在插件层干预结果）
- 不引入 LLM 在线打分（避免延迟与成本）
- 不做通用搜索引擎爬虫管理、引擎健康监控
- 不替换 SearXNG 原生排名（仅在最终输出前叠加二次排序）
- 不实现跨实例分布式配置同步

## Decisions

### 决策 1：重排入口选择 `post_search` 而非 `on_result`

**选择**：在 `post_search` 钩子中对聚合后的完整结果列表进行批量重排。

**理由**：`on_result` 是逐条结果回调，无法获知全量结果分布，难以做相对排序；`post_search` 拿到的是已聚合、去重后的 `result_container.results`，此时原生排名（引擎得分 × 权重 × 可靠性）已计算完毕，最适合叠加二次排序。

**备选方案**：
- `on_result` 逐条打分： rejected，无法做相对重排
- `pre_search` 改写查询：rejected，无法影响已返回结果的排序，且改写查询会污染引擎请求

### 决策 2：双通道串联架构（规则 → 向量）

**选择**：重排流程为 `规则重排（必经） → 向量重排（可选）`，两通道串联。规则层操作 URL（正则匹配域名）；向量层操作**结果正文**（`title` + `content`），不使用 URL 作为语义输入。

**理由**：规则层快速、确定性、低成本（正则毫秒级），先做规则重排可以把明显该剔除的黑名单结果移除、把高权威域名前置；再对规则重排后的 Top N 做向量重排，缩小向量服务的输入规模（降低延迟和成本）。两通道职责清晰：规则管「确定性权威度」（基于 URL），向量管「语义相关性」（基于正文）。URL 几乎不含语义信号（一个域名/路径字符串无法判断「这条结果讲的是不是用户问的话题」），把 URL 喂给 Reranker 等于把向量层降级为弱版 URL 匹配，违背引入向量层的初衷；因此向量层必须使用 SearXNG 结果中已有的 `title`/`content` 字段。字段缺失时回退链为 `title + " " + content` → `title` → `content` → `url`（仅作为兜底，保证不抛错）。

**备选方案**：
- 仅规则重排：rejected，无法解决「权威域名但与查询不相关」的语义问题
- 仅向量重排：rejected，向量服务不可用时完全失效，且无法表达「政府官网永远优先」这类硬性策略
- 并行两通道后加权融合：rejected，复杂度高，且规则与向量分数不在同一量纲，融合权重难调
- 向量层用 URL 作为 text：rejected，URL 无语义信号，实测会让 Reranker 退化成 URL 匹配（曾作为默认实现，被端到端审查发现并废弃）

### 决策 3：最终分数 = 原生分数 × 规则系数，向量层重排后保持原生分数作为次序锚点

**选择**：规则层不替换原生分数，而是乘以权重系数（`score × coefficient`）；向量层对 Top N 重排后，按向量相关性重排顺序，但保留原生分数作为同分时的稳定排序锚点（避免完全打乱原生体验）。

**理由**：保留原生分数作为基准，可保证重排失败或向量服务不可用时，结果回退到接近原生体验；规则系数乘法叠加是最小侵入式干预，可解释性强。

**备选方案**：
- 规则层完全替换为自定义分数：rejected，丢失原生信号，难以调参
- 向量层用分数加权融合：rejected，分数量纲不一致

### 决策 4：配置存储用 PostgreSQL，热更新通过 TTL 缓存 + 轮询

**选择**：插件进程内维护一份配置的内存缓存（TTL 默认 30s），每次搜索时检查 TTL 过期则从 PG 拉取最新配置；配置 UI 写入 PG 后，最长 30s 内生效。

**理由**：
- PG 提供事务性、结构化存储，适合规则/意图/黑名单等关系型数据
- 进程内缓存 + TTL 避免每次搜索都查库（搜索 QPS 高于配置写入频率数个数量级）
- 30s TTL 在「配置生效实时性」与「DB 负载」间取平衡；用户可配置 TTL

**备选方案**：
- 每次搜索实时查 PG：rejected，增加每次搜索的 DB 延迟
- PG LISTEN/NOTIFY 实时推送：备选，实时性更好但增加连接复杂度，留作未来优化
- 配置文件 + 文件监听：rejected，无法支持 Web UI 写入，且多实例同步困难

### 决策 5：向量服务接口约定支持三种协议

**选择**：定义一个通用 Reranker HTTP 接口约定（`POST /rerank`），通过 `vector_protocol` 配置项支持三种主流协议形态：
- `generic`（默认）：`{query, documents:[{id,text}], top_n}` / `{results:[{id,score}]}`，兼容 HuggingFace TEI、自部署服务
- `jina`：`{query, texts:[str], top_n}` / 顶层数组 `[{index,score}]`，兼容 Jina v3、BGE-reranker 风格服务（实测 192.168.2.79:8080 即此协议）
- `cohere`：`{query, documents:[str], top_n}` / `{results:[{index,relevance_score}]}`，兼容 Cohere `/v1/rerank`
通过 `base_url` + `api_key` + `protocol` 三个配置项组合接入任意服务。

**理由**：避免硬绑定单一服务商；实测发现不同 reranker 服务的请求/响应字段名差异显著（Jina 用 `texts`+`index`，Cohere 用 `documents`+`relevance_score`，TEI 用 `{id,text}`+`{id,score}`），与其强求用户写适配层，不如在插件内建多协议支持。协议选择是纯字符串配置，零额外依赖。

**备选方案**：
- 直接调用 Cohere SDK：rejected，厂商锁定
- 仅支持 generic 协议、要求用户自写适配层：rejected，实测 Jina v3 服务（192.168.2.79:8080）即不兼容 generic 格式，强求适配层违背「轻量接入」目标
- 插件内嵌 Embedding 模型：rejected，Python 侧加载模型增加 SearXNG 容器资源负担，与「轻量插件」目标冲突

### 决策 6：意图路由用关键词匹配，不引入分类模型

**选择**：意图路由通过「关键词 → 意图」映射表（如包含「游戏」「steam」「购买」→ `gaming` 意图），每个意图关联一组 URL 正则规则；关键词匹配为子串包含（大小写不敏感），支持多个意图命中时按优先级取第一个。

**理由**：关键词匹配简单、可解释、零延迟、配置友好；引入分类模型违背「不引入 LLM/在线打分」约束。

**备选方案**：
- Embedding 分类器：rejected，增加延迟与依赖，且违背约束
- 正则意图匹配：备选，可后续作为关键词匹配的补充（规则存储已支持正则字段）

### 决策 7：Web 配置系统用 Next.js App Router + 静态 Token 中间件

**选择**：Next.js App Router（Bun.js 运行时），所有 API route 与受保护页面经一个中间件校验 `Authorization: Bearer <token>` 或 Cookie 中的 token；token 通过环境变量（`AUTORERANKER_TOKEN`）配置的静态字符串，不读取 `settings.yml`。

**理由**：App Router 统一前后端；静态 Token 满足「极简准入」需求，无需引入用户表/会话/JWT；Bun.js 启动快、内存占用低。

**备选方案**：
- NextAuth.js 完整登录：rejected，违背「不实现复杂登录」约束
- Basic Auth：备选，但浏览器原生 UI 体验差

### 决策 8：配置数据模型（PostgreSQL Schema）

**选择**：采用以下表结构持久化配置，所有表通过迁移文件创建，初始版本号写入 `config_meta`。

- `intents` — 意图定义
  - `id` SERIAL PK
  - `name` VARCHAR(64) UNIQUE NOT NULL（如 `gaming`、`programming`、`news`，kebab-case）
  - `description` TEXT
  - `priority` INT NOT NULL DEFAULT 100（数值小者优先；通用意图 priority=0 兜底）
  - `enabled` BOOLEAN NOT NULL DEFAULT TRUE
  - `created_at` / `updated_at` TIMESTAMPTZ

- `intent_keywords` — 意图关键词（一对多）
  - `id` SERIAL PK
  - `intent_id` INT FK→intents.id ON DELETE CASCADE
  - `keyword` VARCHAR(64) NOT NULL（大小写不敏感匹配，存储原值）
  - UNIQUE(`intent_id`, `keyword`)

- `rules` — 重排规则（统一表，覆盖通用规则、意图专属规则、黑名单）
  - `id` SERIAL PK
  - `pattern` TEXT NOT NULL（Python 正则，匹配 result.url）
  - `coefficient` NUMERIC(4,2) NOT NULL CHECK(coefficient BETWEEN 0.0 AND 10.0)
  - `priority` INT NOT NULL DEFAULT 100（数值小者优先，规则按此升序遍历，取首个命中）
  - `intent_id` INT FK→intents.id NULL（NULL 表示通用规则，对所有查询生效；非 NULL 表示仅在该意图命中时应用）
  - `enabled` BOOLEAN NOT NULL DEFAULT TRUE
  - `description` TEXT
  - `created_at` / `updated_at` TIMESTAMPTZ
  - INDEX on (`enabled`, `priority`)、INDEX on (`intent_id`)

- `config_meta` — 配置元数据（单行，id 固定为 1）
  - `id` INT PK DEFAULT 1
  - `version` BIGINT NOT NULL DEFAULT 1（任意 CUD 操作触发 `version = version + 1`）
  - `force_reload` BOOLEAN NOT NULL DEFAULT FALSE（Web UI「立即刷新」置位；插件检测后复位）
  - `updated_at` TIMESTAMPTZ

**理由**：
- 黑名单不单独建表，作为 `coefficient=0` 的规则统一管理（spec `config-admin-ui` 中黑名单视图为 rules 的过滤投影：`WHERE coefficient=0`），避免数据冗余与双写一致性
- 意图关键词拆为独立表（一对多）便于 CRUD 与去重；匹配时加载到内存做大小写不敏感子串匹配
- `config_meta.version` 支持「先查版本号再决定是否全量拉取」的增量检查，降低 TTL 刷新的 DB 负载
- `coefficient` 用 NUMERIC(4,2) + CHECK 约束双保险（DB 层兜底），范围 0.0~10.0

**备选方案**：
- 黑名单单独建表：rejected，与 `coefficient=0` 语义重复，需双向同步
- 关键词存为 `ARRAY` 或 JSON：rejected，CRUD 与去重不如关系表直观，且不利于按关键词查询
- 用 `updated_at` 时间戳代替版本号：备选，但时间戳精度与跨时区处理麻烦，版本号递增更可靠

## Risks / Trade-offs

- **[向量服务延迟波动]** → 设置超时（默认 500ms）+ 失败静默降级回规则重排结果；超时与失败均记日志但不抛错
- **[PG 不可用导致插件失效]** → 插件启动时加载配置到内存，运行时优先用内存缓存；PG 不可用时沿用上次缓存，缓存过期且 PG 仍不可用则降级为「仅原生排序」并记错误日志
- **[正则规则误伤]** → 提供「测试匹配」功能（Web UI 输入 URL 预览命中规则与系数）；规则按优先级有序匹配，取首个命中
- **[配置热更新延迟]** → TTL 默认 30s 可接受；提供 Web UI 的「立即刷新」按钮（调用插件暴露的内部刷新接口或写 PG 的 `force_reload` 标志位）
- **[多 SearXNG 实例配置不一致]** → 所有实例读同一 PG，TTL 内可能短暂不一致；属可接受权衡，非强一致场景
- **[静态 Token 泄露]** → Token 通过环境变量注入不硬编码；建议配置系统仅在内网或 TLS 反代后暴露；文档明确提示风险
- **[原生分数被规则系数过度放大]** → 系数默认范围限定 0.0~10.0，超出范围在 UI 校验拦截；提供「仅降权不加权」的保守模式开关
- **[向量重排打乱原生体验]** → 向量层仅重排 Top N（默认 20~25），N 之外的保持规则重排顺序；同向量分时回退原生分数排序
