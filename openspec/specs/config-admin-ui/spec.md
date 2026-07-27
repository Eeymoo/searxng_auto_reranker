# config-admin-ui Specification

## Purpose
TBD - created by archiving change add-auto-reranker-plugin. Update Purpose after archive.
## Requirements
### Requirement: 静态 Token 准入

系统 SHALL 通过静态 Token 对所有配置管理页面与 API 进行准入校验，未携带正确 Token 的请求被拒绝（401）。

#### Scenario: 携带正确 Token 访问受保护资源

- **WHEN** 请求携带 `Authorization: Bearer <正确 token>` 或 Cookie 中含正确 token
- **THEN** 请求被放行，返回对应页面或 API 响应

#### Scenario: 未携带或携带错误 Token

- **WHEN** 请求未携带 Token 或 Token 与配置的不一致
- **THEN** 页面请求重定向到登录页，API 请求返回 401 Unauthorized

#### Scenario: Token 通过环境变量注入

- **WHEN** 部署配置系统
- **THEN** Token 通过环境变量（如 `AUTORERANKER_TOKEN`）读取，不硬编码在代码或配置文件中

### Requirement: 规则 CRUD

系统 SHALL 提供 URL 正则规则的创建、读取、更新、删除功能，支持权重系数范围校验（0.0 ~ 10.0）。

#### Scenario: 创建规则

- **WHEN** 在规则管理页面填写正则 `.*\.gov\.cn/.*`、系数 2.0、优先级 10 并提交
- **THEN** 规则被创建并持久化到 PostgreSQL，规则列表刷新显示新规则

#### Scenario: 校验失败拒绝创建

- **WHEN** 提交的系数为 15.0（超出 0.0~10.0）或正则语法非法
- **THEN** 表单显示校验错误，规则不被创建

#### Scenario: 编辑规则

- **WHEN** 在规则列表点击某规则的编辑，修改系数后提交
- **THEN** 规则被更新并持久化，列表显示新系数

#### Scenario: 删除规则

- **WHEN** 在规则列表点击某规则的删除并确认
- **THEN** 规则被从 PostgreSQL 删除，列表不再显示

### Requirement: 意图与关键词管理

系统 SHALL 提供意图的创建、编辑、删除功能，每个意图可管理其关键词列表与关联的规则集合。

#### Scenario: 创建意图并添加关键词

- **WHEN** 在意图管理页面创建 `gaming` 意图，添加关键词「游戏」「购买」
- **THEN** 意图与关键词被持久化，意图详情页显示这些关键词

#### Scenario: 为意图添加专属规则

- **WHEN** 在 `gaming` 意图详情页添加规则 `.*store\.steampowered\.com/.*` 系数 2.5
- **THEN** 该规则关联到 `gaming` 意图并持久化，仅在查询命中该意图时应用

### Requirement: 黑名单管理

系统 SHALL 提供黑名单（权重为 0 的剔除规则）的单独管理视图，便于快速拉黑域名/URL 模式。

#### Scenario: 添加黑名单规则

- **WHEN** 在黑名单管理页面添加 `.*spam-site\.example/.*`
- **THEN** 该规则以系数 0 持久化，规则重排时匹配的结果被剔除

#### Scenario: 查看与删除黑名单

- **WHEN** 在黑名单列表查看或删除某条
- **THEN** 列表实时反映 PostgreSQL 状态，删除后该 URL 模式不再被剔除

### Requirement: 规则测试预览

系统 SHALL 提供规则测试功能，输入 URL 与（可选）查询，预览命中的规则、应用的系数与最终排序效果。

#### Scenario: 测试 URL 命中规则

- **WHEN** 在测试页面输入 URL `https://www.example.gov.cn/news` 并点击测试
- **THEN** 系统显示命中的规则（如 `.*\.gov\.cn/.*` 系数 2.0）、应用后的系数、是否被剔除（系数 0）

#### Scenario: 未命中任何规则

- **WHEN** 输入的 URL 不匹配任何启用规则
- **THEN** 系统显示「未命中规则，系数 1.0」

### Requirement: 立即刷新配置

系统 SHALL 提供「立即刷新」按钮，触发插件在下一次搜索时强制重新加载配置（绕过 TTL 等待）。

#### Scenario: 点击立即刷新

- **WHEN** 运维者点击「立即刷新」按钮
- **THEN** 系统通过设置 PG 元数据的强制刷新标志位或调用插件刷新接口，使插件在下次搜索时绕过 TTL 重新加载配置

