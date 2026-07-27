# intent-routing Specification

## Purpose
TBD - created by archiving change add-auto-reranker-plugin. Update Purpose after archive.
## Requirements
### Requirement: 意图识别

系统 SHALL 通过关键词子串匹配（大小写不敏感）将查询映射到一个或多个意图，每条意图关联一组专用的 URL 正则规则集合，叠加在通用规则之上。

#### Scenario: 命中单个意图

- **WHEN** 查询包含某意图的关键词之一（如查询「赛博朋克2077 购买」命中 `gaming` 意图的关键词「购买」）
- **THEN** 规则重排阶段在通用规则之外，额外应用 `gaming` 意图专属规则集合（如 Steam 商店加权）

#### Scenario: 未命中任何意图

- **WHEN** 查询不包含任何意图的关键词
- **THEN** 规则重排阶段仅应用通用规则集合

### Requirement: 多意图优先级

系统 SHALL 在查询命中多个意图时，按意图的优先级字段取最高优先级者作为本次查询的有效意图。

#### Scenario: 命中多个意图按优先级取一

- **WHEN** 查询同时命中 `gaming`（优先级 10）与 `programming`（优先级 20）
- **THEN** 系统选择优先级数值更小的 `gaming` 作为有效意图，应用其规则集合；另一意图的规则不应用

#### Scenario: 意图关键词可配置

- **WHEN** 通过配置 UI 为某意图新增/删除关键词（如给 `gaming` 添加「折扣」）
- **THEN** 变更持久化到 PostgreSQL，并在配置 TTL 过期后的下次搜索生效

### Requirement: 意图数据模型

系统 SHALL 支持存储与读取意图数据，每个意图包含：意图 ID、名称、关键词列表、优先级、启用状态、关联规则集合。

#### Scenario: 创建意图并关联规则

- **WHEN** 通过配置 UI 创建 `gaming` 意图（关键词：游戏、购买、steam；优先级 10）并为其添加规则（`.*store\.steampowered\.com/.*` 系数 2.5）
- **THEN** 意图与其规则一并持久化，可在后续搜索的意图路由中被加载

#### Scenario: 禁用意图不再参与路由

- **WHEN** 一个意图的 `enabled` 字段被设为 false
- **THEN** 后续意图识别跳过该意图，即便查询包含其关键词也不应用其规则集合

