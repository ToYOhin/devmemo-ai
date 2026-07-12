# DevMemo AI 决策记录

## ADR-001：保留 Memos upstream 边界

- 状态：Accepted
- 决策：Memos 根目录、Go Store、Proto 和 React Web 视为上游区；AI 能力通过 Webhook 和独立 HTTP 服务接入。
- 原因：降低升级冲突，避免把第三方模型依赖带入 Memos 核心。
- 影响：AI 派生数据由 `ai-service` 管理，不能假设 Memos 数据库存在 `ai_summary` 列。

## ADR-002：Phase 1 使用 SQLite 保存 AI 派生结果

- 状态：Accepted for MVP
- 决策：`ai-service` 使用 `ai_notes` SQLite 表，按 `memo_id` upsert。
- 原因：零额外服务、便于本地演示；Qdrant 只在 RAG 阶段承担向量索引。
- 后续：当任务队列、多人部署或备份需求出现时，再评估 Postgres。

## ADR-003：LLM 通过薄适配器隔离

- 状态：Accepted
- 决策：业务层只依赖 provider-neutral 的生成接口；OpenAI、Ollama、deterministic 实现放在适配器层。
- 原因：本地无 key 时可测试，未来可替换服务商。

## ADR-004：RAG 优先采用 FastEmbed + Qdrant

- 状态：Planned
- 决策：Phase 3 优先评估 FastEmbed 生成本地 embedding，使用 qdrant-client 访问 Qdrant。
- 原因：保持当前 Qdrant Compose 设计，CPU 可运行，依赖面小。
- 前置：先定义 embedding/vectorstore 接口和评估集，不直接把 SDK 类型泄漏到 domain。

## ADR-005：每个切片必须产生下一步 Prompt

- 状态：Accepted
- 决策：`PROJECT_STATUS`、`CHANGELOG_AI`、`HANDOFF`、`NEXT_STAGE_PROMPT` 是每个完成切片的固定交付物。
- 原因：降低跨窗口继续工作的上下文成本，避免阶段标签和验证事实过期。

## ADR-006：模板解析失败回退普通 Memo

- 状态：Accepted
- 决策：只有显式 `type` 标记且字段合法时才返回结构化模板；无标记、空内容或不支持语言都回退为 `plain`。
- 原因：模板能力不能阻断 Memos 原有保存、搜索和 Markdown 展示。
- 影响：Phase 2 的持久化必须同时保存原始 Markdown 和解析状态，不能只保存结构化结果。

## ADR-007：结构化模板由 AI Service 自有 SQLite 管理

- 状态：Accepted for Phase 2
- 决策：新增 `memo_templates` 表，按 `memo_id` 唯一 upsert，保存 `kind`、JSON `payload`、`raw_content`、创建和更新时间。
- 原因：不修改 Memos 核心数据库，同时保留原始 Markdown 以支持解析器升级和重建。
- 影响：Memos React UI 必须通过 AI Service API 读取模板，不能直接访问 SQLite。
