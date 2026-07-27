# rule-rerank Specification

## Purpose
TBD - created by archiving change add-auto-reranker-plugin. Update Purpose after archive.
## Requirements
### Requirement: 规则重排执行

系统 SHALL 在 SearXNG `post_search` 钩子中对聚合后的结果列表执行规则重排，按 URL 正则规则匹配结果并应用对应的权重系数。

#### Scenario: 命中加权规则时结果前置

- **WHEN** 一条结果的 URL 匹配到权重系数 > 1.0 的规则（如 `.*\.gov\.cn/.*` 系数 2.0）
- **THEN** 该结果的最终分数 = 原生分数 × 权重系数，排序相应前置

#### Scenario: 命中权重为 0 规则时结果被剔除

- **WHEN** 一条结果的 URL 匹配到权重系数 = 0 的规则
- **THEN** 该结果从结果列表中完全移除，不再出现在最终输出中

#### Scenario: 多条规则按优先级首个命中

- **WHEN** 一条结果的 URL 同时匹配多条规则
- **THEN** 系统按规则的优先级（priority 字段升序）取首条命中规则应用其权重系数，其余规则忽略

#### Scenario: 未命中任何规则保持原生排序

- **WHEN** 一条结果的 URL 未匹配任何规则
- **THEN** 该结果的权重系数视为 1.0，最终分数 = 原生分数，保持原排序位置

#### Scenario: 同分结果稳定排序

- **WHEN** 多条结果经规则系数调整后最终分数相同
- **THEN** 系统按原生分数降序作为次序锚点，保持稳定排序（不随机抖动）

### Requirement: 规则数据模型

系统 SHALL 支持存储与读取规则数据，每条规则包含：规则 ID、URL 正则、权重系数、所属意图（可为通用）、优先级、启用状态、描述。

#### Scenario: 创建规则

- **WHEN** 通过配置 UI 或 API 提交一条新规则（正则 `.*\.gov\.cn/.*`，系数 2.0，优先级 10）
- **THEN** 规则被持久化到 PostgreSQL，并可在后续搜索的规则重排中被加载

#### Scenario: 权重系数范围校验

- **WHEN** 提交的权重系数不在 0.0 ~ 10.0 范围内
- **THEN** 系统拒绝创建/更新并返回校验错误

#### Scenario: 禁用规则不再生效

- **WHEN** 一条规则的 `enabled` 字段被设为 false
- **THEN** 后续搜索的规则重排跳过该规则，URL 即便匹配也不应用其系数

