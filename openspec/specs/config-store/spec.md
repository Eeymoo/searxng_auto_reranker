# config-store Specification

## Purpose
TBD - created by archiving change add-auto-reranker-plugin. Update Purpose after archive.
## Requirements
### Requirement: 配置持久化

系统 SHALL 将重排规则、意图、黑名单、权重系数等配置持久化到 PostgreSQL，插件运行时从 PG 读取配置。

#### Scenario: 配置写入后可读取

- **WHEN** 配置 UI 或外部写入一条规则到 PostgreSQL
- **THEN** 插件在下一次配置刷新时能从 PG 读取到该规则并应用到规则重排

#### Scenario: PG 不可用时沿用缓存降级

- **WHEN** 配置 TTL 过期且 PostgreSQL 不可达
- **THEN** 插件沿用上一次成功加载的内存缓存继续运行，并记录一条错误日志；不向用户抛错

#### Scenario: PG 不可用且无缓存时降级为原生排序

- **WHEN** 插件启动时 PG 不可达且内存中无任何缓存
- **THEN** 插件降级为「仅原生排序」（不应用任何规则与向量重排），并记录错误日志，搜索流程不中断

### Requirement: 配置热更新

系统 SHALL 支持配置热更新，配置写入 PG 后无需重启 SearXNG 即可生效，生效延迟受 TTL 控制。

#### Scenario: TTL 过期后自动刷新

- **WHEN** 配置写入 PG 后经过 TTL（默认 30s）
- **THEN** 下一次搜索触发配置刷新，新配置被加载到内存并应用

#### Scenario: TTL 未过期沿用旧配置

- **WHEN** 配置写入 PG 后未经过 TTL
- **THEN** 插件沿用当前内存缓存，不查询 PG（降低 DB 负载）

### Requirement: 配置缓存

系统 SHALL 在插件进程内存中维护配置缓存，TTL 可配置（默认 30 秒），每次搜索检查 TTL 是否过期。

#### Scenario: TTL 可配置

- **WHEN** 运维者在 `settings.yml` 将 `auto_reranker.cache_ttl` 设为 10
- **THEN** 配置缓存的 TTL 变为 10 秒，刷新频率相应提高

#### Scenario: 缓存命中时不查库

- **WHEN** TTL 未过期（缓存命中）
- **THEN** 搜索的配置读取直接返回内存缓存，不发起 PG 查询

### Requirement: 配置元数据

系统 SHALL 维护一份配置元数据表，记录配置版本号与最后更新时间，用于判断是否需要重新加载。

#### Scenario: 配置变更后版本号递增

- **WHEN** 任意规则/意图/黑名单被创建、更新或删除
- **THEN** 元数据表的版本号递增、最后更新时间刷新

#### Scenario: 插件比较版本号决定是否拉取

- **WHEN** TTL 过期触发刷新
- **THEN** 插件先查询元数据版本号，与内存缓存版本号相同则跳过全量拉取，不同则拉取最新配置

### Requirement: 配置数据模型

系统 SHALL 在 PostgreSQL 中维护以下表结构以持久化配置：`intents`（意图定义：id、name 唯一、description、priority、enabled、时间戳）、`intent_keywords`（意图关键词一对多：id、intent_id 外键级联删除、keyword，intent_id+keyword 唯一）、`rules`（统一重排规则表：id、pattern 正则、coefficient NUMERIC(4,2) CHECK 0.0~10.0、priority、intent_id 可空表示通用规则、enabled、description、时间戳）、`config_meta`（单行元数据：version 自增、force_reload 标志、updated_at）。黑名单 SHALL 作为 `coefficient=0` 的规则存储于 `rules` 表，不单独建表。

#### Scenario: 黑名单以 coefficient=0 规则存储

- **WHEN** 通过黑名单管理视图添加一条 `.*spam-site\.example/.*`
- **THEN** 该记录以 `coefficient=0` 写入 `rules` 表（intent_id 可为 NULL），不存在独立的黑名单表

#### Scenario: coefficient CHECK 约束生效

- **WHEN** 尝试直接向 `rules` 表插入 coefficient=15.0（超出 0.0~10.0）的记录
- **THEN** PostgreSQL 拒绝该写入（CHECK 约束违约），与 UI/API 校验形成双保险

#### Scenario: 删除意图级联删除关联数据

- **WHEN** 删除一个 `gaming` 意图（`intents` 表删除该行）
- **THEN** `intent_keywords` 中该意图的关键词行被级联删除（ON DELETE CASCADE）；`rules` 表中 `intent_id` 指向该意图的规则，其 `intent_id` 被置为 NULL（变为通用规则）或按 UI 选择删除

#### Scenario: 通用规则与意图规则区分

- **WHEN** 创建一条规则且未指定 intent_id
- **THEN** 该规则的 `intent_id` 为 NULL，规则重排时对所有查询生效（通用规则）；指定 intent_id 的规则仅在该意图命中时生效

#### Scenario: 关键词唯一约束

- **WHEN** 为同一意图重复添加已存在的关键词
- **THEN** 写入被 `intent_id + keyword` 唯一约束拒绝，UI 提示重复

