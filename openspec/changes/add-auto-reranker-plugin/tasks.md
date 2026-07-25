## 1. 项目脚手架与依赖

- [x] 1.1 初始化仓库结构：`searx/plugins/auto_reranker/`（Python 插件）、`config-ui/`（Next.js 配置系统）、`migrations/`（PG 迁移）、`docs/`、`docker/`
- [x] 1.2 创建插件 Python 包骨架：`__init__.py`、`plugin.py`、`rule_engine.py`、`vector_engine.py`、`intent_router.py`、`config_loader.py`、`pg_client.py`，补全 `pyproject.toml` 或 `requirements.txt`（`psycopg2-binary`、`httpx`）
- [x] 1.3 初始化 Next.js 配置系统：`bun create next-app config-ui`，集成 shadcn/ui，配置 App Router、TypeScript、Tailwind
- [x] 1.4 编写 PostgreSQL schema 迁移文件（`migrations/001_init.sql`）：建 `intents`（id、name 唯一、description、priority、enabled、时间戳）、`intent_keywords`（intent_id FK 级联删除、keyword，intent_id+keyword 唯一约束）、`rules`（pattern、coefficient NUMERIC(4,2) CHECK 0.0~10.0、priority、intent_id 可空、enabled、description、时间戳、`(enabled,priority)` 与 `intent_id` 索引）、`config_meta`（单行 version 自增、force_reload、updated_at），并写入初始版本号行
- [x] 1.5 编写顶层 README 与 docker-compose（SearXNG + PostgreSQL + config-ui 三容器编排，挂载插件目录）

## 2. 配置存储层（config-store）

- [x] 2.1 实现 `pg_client.py`：连接池、健康检查、`PG不可用时异常`，连接参数从 `settings.yml` 或环境变量读取
- [x] 2.2 实现 `config_loader.py`：从 PG 拉取全量配置（规则、意图、关键词、黑名单、元数据）到内存对象
- [x] 2.3 实现内存缓存 + TTL 机制（默认 30s，可配置），TTL 命中返回缓存、过期查询版本号决定是否全量拉取
- [x] 2.4 实现「PG 不可用沿用缓存」与「无缓存降级为原生排序」两条降级路径，并记录日志
- [x] 2.5 实现配置元数据版本号比对：版本号相同跳过拉取，不同全量拉取并更新缓存版本
- [x] 2.6 编写 config_loader 单元测试（TTL 命中/过期、版本号比对、PG 故障降级）
- [x] 2.7 **修正 force_reload 绕过 TTL**（spec 审查发现的 B1 偏差）：`config_loader.get()` 当前先做 TTL 短路再读 `force_reload`，导致「立即刷新」标志在 TTL 窗口内被忽略；需让 `force_reload` 检查发生在 TTL 短路之前（或每次 `get()` 都先 cheap 查一次 `config_meta.force_reload`），使运维者点击后下次搜索立即生效

## 3. 规则重排层（rule-rerank）

- [x] 3.1 实现 `rule_engine.py`：按优先级遍历启用规则，对每条结果 URL 做正则匹配，取首个命中的系数
- [x] 3.2 实现权重为 0 的剔除逻辑：系数 0 的命中结果从结果列表移除
- [x] 3.3 实现最终分数计算 `score × coefficient`，未命中视为系数 1.0
- [x] 3.4 实现稳定排序：最终分数降序，同分回退原生分数降序
- [x] 3.5 预编译正则缓存（避免每次搜索重新编译），规则变更时随配置刷新重建
- [x] 3.6 编写 rule_engine 单元测试（加权前置、黑名单剔除、多规则优先级、未命中保持、同分稳定排序）

## 4. 意图路由层（intent-routing）

- [x] 4.1 实现 `intent_router.py`：查询关键词子串匹配（大小写不敏感），返回命中意图列表
- [x] 4.2 实现多意图优先级裁决：命中多个时按 priority 升序取首条
- [x] 4.3 实现意图规则集合叠加：有效意图的规则集合与通用规则集合合并后传入 rule_engine（注意优先级字段的全局排序）
- [x] 4.4 编写 intent_router 单元测试（单意图命中、多意图优先级、无意图仅用通用规则、禁用意图不参与）

## 5. 向量重排层（vector-rerank）

- [x] 5.1 实现 `vector_engine.py`：构造标准请求（`POST {base_url}/rerank`、Bearer api_key、`{query, documents, top_n}`）
- [x] 5.2 实现取规则重排后前 N 条（默认 N=20）送入向量服务，按返回分数重排这 N 条；N 外保持规则顺序
- [x] 5.3 实现超时（默认 500ms）与错误处理：捕获 `httpx.TimeoutException` 与非 2xx，静默降级回规则重排结果，记录警告日志
- [x] 5.4 实现同向量分回退原生分数排序
- [x] 5.5 实现开关（`auto_reranker.vector_enabled`），关闭时直接跳过
- [x] 5.6 编写 vector_engine 单元测试（启用重排、关闭跳过、超时降级、错误降级、同分稳定）
- [x] 5.7 **修正向量层语义文本来源**（spec 审查发现的 B2 偏差）：`vector_engine` 的 `text_of` 默认实现当前用 URL，需改为 `title + " " + content`，回退链 `title` → `content` → `url`；`plugin.py` 的 `post_search` 需把 SearXNG 结果的 `title`/`content` 字段投影到 `ScoredResult`（或传入 `text_of` 闭包），不再只传 `url`/`score`

## 6. SearXNG 插件集成

- [x] 6.1 实现 `plugin.py`：继承 `Plugin` 基类，声明 `plugin_hooks = ['post_search']`
- [x] 6.2 在 `post_search` 中编排流程：检查配置 TTL → 加载配置 → 意图路由 → 规则重排 → 向量重排 → 写回 `result_container`
- [x] 6.3 实现插件参数解析（`settings.yml` 的 `auto_reranker` 节：PG 连接串、向量服务 base_url/api_key、top_n、超时、TTL、开关）
- [x] 6.4 实现插件 `init` 阶段的预加载配置与降级保护（PG 不可用不阻塞插件注册）
- [x] 6.5 编写 `settings.yml` 示例片段（`plugins: [...]` 追加全限定类名、`auto_reranker:` 节字段）
- [x] 6.6 集成测试：在本地 SearXNG 实例加载插件，验证「今天热点新闻」「微博热搜」等查询结果改善

## 7. Web 配置系统后端 API（config-ui）

- [x] 7.1 实现静态 Token 中间件：校验 `Authorization: Bearer` 或 Cookie，失败 401 或重定向登录页
- [x] 7.2 实现 PG 客户端（Node `pg` 或 Prisma），连接串从环境变量读取
- [x] 7.3 实现 `/api/rules` CRUD（GET 列表、POST 创建、PATCH 更新、DELETE 删除），含系数 0.0~10.0 校验与正则合法性校验
- [x] 7.4 实现 `/api/intents` CRUD + `/api/intents/:id/keywords` + `/api/intents/:id/rules`（意图与关联资源管理）
- [x] 7.5 实现 `/api/blacklist` CRUD（本质为系数 0 的规则，但单独视图）
- [x] 7.6 实现 `/api/test` 规则测试预览（输入 URL + 可选查询，返回命中规则、系数、是否剔除）
- [x] 7.7 实现 `/api/refresh` 立即刷新（写 `config_meta.force_reload=true` 标志位供插件下次搜索检测）
- [x] 7.8 编写 API 单元测试（CRUD、校验失败、Token 准入拒绝）
- [x] 7.9 **修正 Cookie 名称拼写**（M2）：`lib/auth.ts`、`lib/api.ts`、`test/auth.test.ts` 中的 `autoreareranker_token`（多了个 "re"）统一改为 `auto_reranker_token`
- [x] 7.10 **补 `/api/intents/:id/rules` POST**（M3）：当前只有 GET；补 POST 在该路径下创建意图专属规则（等价于 `POST /api/rules` 带 `intent_id`，但符合 REST 嵌套语义）

## 8. Web 配置系统前端 UI（config-ui）

- [x] 8.1 实现登录页（输入 Token，校验后写 HttpOnly Cookie，重定向到规则管理）
- [x] 8.2 实现整体布局（侧边导航：规则、意图、黑名单、测试、刷新）+ shadcn/ui 组件集成
- [x] 8.3 实现规则管理页（表格 + 新建/编辑弹窗 + 删除确认，字段：正则、系数、优先级、启用、描述）
- [x] 8.4 实现意图管理页（意图列表 + 详情页含关键词编辑与意图专属规则列表）
- [x] 8.5 实现黑名单管理页（简化表格，URL 模式 + 删除）
- [x] 8.6 实现规则测试页（URL + 查询输入，结果区显示命中规则与系数）
- [x] 8.7 实现「立即刷新」按钮（调用 `/api/refresh`，Toast 反馈结果）
- [x] 8.8 前端表单校验（系数 0.0~10.0、正则语法预检）与错误提示
- [x] 8.9 **新增 Next.js `middleware.ts` 服务端保护**（spec 审查发现的 B3 偏差）：当前 dashboard 页面仅靠客户端 `useEffect` 跳转，对 `curl` 等非 JS 客户端直接吐 HTML；需新增 `config-ui/middleware.ts`，对 `/rules`、`/intents`、`/blacklist`、`/test` 及其子路径做服务端 token 校验（读 Cookie），未授权则 302 重定向到 `/login`；`/login`、`/api/*`、静态资源放行
- [x] 8.10 **登录改用 HttpOnly Cookie**（spec 审查发现的 M1 偏差）：`/login` 提交 token 校验通过后，由服务端路由（改为 `app/login/actions.ts` 的 server action 或 `/api/login` 路由）写 `Set-Cookie: auto_reranker_token=<token>; HttpOnly; SameSite=Strict; Path=/; Max-Age=...`；前端不再写 `localStorage`（保留 localStorage 兜底可选，但 Cookie 是主路径，使中间件能在服务端读到）

## 9. 部署、文档与验收

- [x] 9.1 完善 docker-compose：SearXNG（挂载插件与 settings.yml 覆盖）、PostgreSQL（带 volume 与初始化迁移）、config-ui（注入 Token 环境变量）
- [x] 9.2 编写 `docs/INSTALL.md`：环境变量、PG 初始化、settings.yml 配置、插件注册、Token 安全建议
- [x] 9.3 编写 `docs/CONFIG_GUIDE.md`：典型中文场景规则示例（政府官网、Steam、官方文档、黑名单示例）
- [x] 9.4 编写 `docs/VECTOR_SERVICE.md`：Reranker 接口约定、自部署 BGE-reranker 示例、Cohere/Jina 对接说明
- [x] 9.5 端到端验收：按成功约束逐条验证（规则排序、向量排序、黑名单、热更新、性能）
- [x] 9.6 编写 `docs/TROUBLESHOOTING.md`：常见问题（PG 不可用、向量超时、规则误伤、Token 遗失）
