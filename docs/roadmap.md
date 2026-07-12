# DevMemo AI 二次开发路线

## 总原则

1. Memos 根目录、`server/`、`store/`、`proto/`、`web/` 视为上游区，升级时尽量保持干净。
2. AI 能力只通过 Webhook、HTTP API 和可替换适配器接入，不直接读写 Memos 数据库。
3. 先建立可回滚的垂直切片，再扩展数据模型和 UI。
4. 每个阶段必须有自动化验证和一个独立 commit；未完成能力默认不可见。
5. 每个完成切片必须同步 `PROJECT_STATUS`、`CHANGELOG_AI`、`HANDOFF` 和下一步 Prompt，具体规则见 `docs/DOC_UPDATE_POLICY.md`。

## Phase 0：开发基础（当前进行中）

- Go `1.26.2` 安装到 `G:\Go`，`GOPATH`/`GOCACHE` 使用 `G:\GoWorkspace`。
- Docker Desktop 负责 Memos、AI Service、Qdrant、Ollama 的运行环境。
- Memos 基线固定为 `v0.29.1`，官方源码 remote 保留为 `upstream`。
- 验证门禁：`go test ./...`、`pnpm lint`、`pnpm build`、AI Service pytest、`docker compose config`。

## Phase 1：AI 总结（已完成 MVP）

```text
Memos memo.created / memo.updated
  -> ai-service webhook
  -> LLM provider
  -> ai_notes SQLite upsert
```

下一步增强：Webhook 鉴权、超时/重试、幂等键、失败记录，并把摘要规则从 HTTP 路由移到 `app/services/summarizer.py`。

## Phase 2：开发者 Memo 类型

不改 Memos 核心表，先使用 Memo 内容约定、标签和现有 Markdown 能力：

已完成的最小切片：`ai-service/app/domain` 定义 provider-neutral 的 `CodeSnippet`、`BugReport`、`ParsedMemo`，`app/services/content_parser.py` 解析 frontmatter、type 标记、代码 fence、Bug Report 标题段落和内联字段；解析失败回退为普通 Memo。

已完成的持久化切片：结构化模板写入 AI Service 自有 `memo_templates` 表，按 `memo_id` upsert，并提供读取 API；仍不修改 Memos 核心表。

下一小步：在 Memos React 前端增加最小模板展示/复制 UI，AI Service 不可用时不影响普通 Memo。

- `Code Snippet`：使用 frontmatter 或稳定模板标记 `type=code`，保存 `title/language/code/description`。
- `Bug Report`：使用模板标记 `type=bug`，保存环境、日志、复现步骤、原因和解决方案。
- AI Service 增加 `content_parser`，解析失败时仍按普通 Memo 保存。
- 代码高亮优先复用 Memos 现有 Markdown/highlight 能力。

验收：创建、编辑、搜索、标签过滤和原始 Markdown 展示均不回归。

## Phase 3：Embedding + RAG

```text
Memo webhook -> normalizer/chunker -> embedding provider -> Qdrant upsert
Question -> query embedding -> filtered search -> context -> LLM answer with citations
```

实施顺序：

1. 先实现 `EmbeddingProvider` 和 `VectorStore` 接口，保留 deterministic fake 供测试。
2. 使用 `fastembed` 做 CPU 本地 embedding，记录模型名、维度和距离函数。
3. 使用 `qdrant-client` 做 collection/upsert/query/delete；Qdrant 只存派生索引。
4. 增加重建索引、删除同步、模型升级迁移和召回质量评估集。
5. `/api/ai/chat` 必须返回引用的 Memo UID/时间，不允许只返回无来源答案。

## Phase 4：Memos React UI

- 在 `web/src/` 新增独立 AI feature 区域，不重写编辑器和查询状态。
- 详情页增加摘要卡片、关键词、分类、重新生成按钮。
- 使用现有 Connect/React Query 数据层；AI HTTP API 通过一个 client/hook 封装。
- AI Service 不可用时只显示可重试状态，不影响 Memo 保存。

## Phase 5：可靠性与展示

- outbox/任务队列：Memo 保存不等待 LLM，AI 任务异步执行并可重试。
- 观测：请求耗时、provider、token/cost、失败原因、Qdrant 召回命中率。
- 安全：Webhook 鉴权、密钥脱敏、请求体限制、Prompt 注入边界和删除同步。
- 展示：固定 demo 数据、截图、架构图、CI badge、升级说明和简历项目说明。

## 暂不做

- 不把 LangChain/LlamaIndex 直接放进核心路径。
- 不引入第二个向量库替代 Qdrant。
- 不为了 AI 字段直接修改 Memos 三套数据库迁移。
- 不把 OpenAI/Ollama SDK 类型泄漏到领域层。
