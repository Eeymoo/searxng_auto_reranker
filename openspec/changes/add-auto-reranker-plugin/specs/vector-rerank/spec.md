## ADDED Requirements

### Requirement: 向量重排执行

系统 SHALL 提供可开关的向量重排通道，在规则重排之后对 Top N 结果调用外部 Reranker 服务按查询语义重新打分并重排。系统 SHALL 将结果的标题与正文（而非 URL）作为语义文本发送给 Reranker 服务，URL 仅作为结果标识。

#### Scenario: 启用向量重排时对 Top N 重排

- **WHEN** 向量重排开关开启且 Reranker 服务可用，且规则重排后结果数 > N
- **THEN** 系统取规则重排后的前 N 条（默认 N=20）连同查询发送给 Reranker 服务，按返回的相关性分数重排这 N 条；N 条之外的结果保持规则重排顺序不变

#### Scenario: 关闭向量重排时跳过

- **WHEN** 向量重排开关关闭
- **THEN** 系统跳过向量重排，最终顺序等于规则重排结果

#### Scenario: 语义文本来源优先级

- **WHEN** 系统为某条结果构造发送给 Reranker 的 `text` 字段
- **THEN** 系统按 `title` → `content` → `url` 的优先级取值（即有 `title` 用 `title`，否则有 `content` 用 `content`，二者皆空时回退到 `url`），保证在 SearXNG 结果缺字段时仍能调用服务而不抛错

#### Scenario: 标题与正文都存在时拼接发送

- **WHEN** 某条结果同时含有 `title` 与 `content` 字段
- **THEN** 系统将二者拼接（如 `title + " " + content`）作为 `text` 发送，让 Reranker 同时利用标题（高信号）与正文摘要（补充上下文）

### Requirement: 失败静默降级

系统 SHALL 在 Reranker 服务不可用或超时时静默降级回规则重排结果，不向用户抛错、不阻塞搜索流程。

#### Scenario: Reranker 服务超时降级

- **WHEN** 调用 Reranker 服务超过配置的超时时间（默认 500ms）
- **THEN** 系统放弃本次向量重排，最终顺序回退为规则重排结果，并记录一条警告日志

#### Scenario: Reranker 服务返回错误降级

- **WHEN** Reranker 服务返回非 2xx 状态码或响应体无法解析
- **THEN** 系统放弃本次向量重排，最终顺序回退为规则重排结果，并记录一条警告日志

### Requirement: Reranker 服务接口约定

系统 SHALL 通过通用的 HTTP JSON 协议调用 Reranker 服务，入参为 `{query, documents: [{id, text}], top_n}`，预期返回 `{results: [{id, score}]}`，通过 `base_url` 与 `api_key` 配置。

#### Scenario: 构造标准请求

- **WHEN** 系统向 Reranker 服务发起调用
- **THEN** 请求方法为 POST，目标地址为 `{base_url}/rerank`，请求头携带 `Authorization: Bearer {api_key}`（api_key 非空时），请求体包含 query、documents（id + text，其中 text 按上文「语义文本来源优先级」构造，不是 URL）、top_n

#### Scenario: 同向量分时回退原生分数

- **WHEN** Reranker 返回的多条结果分数完全相同
- **THEN** 这些同分结果按其原生分数降序排列，保证稳定可预期
