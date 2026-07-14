# 开源组件采用记录

| 组件 | 用途 | 决策 | 边界 |
|---|---|---|---|
| Memos | 原有笔记系统 | 保留上游 `v0.29.1` | 不复制源码，不把 AI 逻辑塞进 Store |
| Qdrant | 向量存储和过滤检索 | Phase 3 采用 | 只存派生索引，collection 版本化 |
| qdrant-client | Python Qdrant SDK | Phase 3 采用 | 只允许出现在 `ai-service/app/adapters/qdrant_vector_store.py` |
| FastEmbed | CPU/ONNX embedding | Phase 3 优先采用 | 锁定模型和维度，单独检查模型许可证 |
| Ollama | 本地 LLM runtime | 当前保留 | 通过 `LLMProvider`，不让业务依赖 Ollama API |
| FastAPI | AI Service HTTP 层 | 当前已采用 | 路由只负责协议转换和错误边界 |

Qdrant、qdrant-client 和 FastEmbed 官方仓库为 Apache-2.0；FastEmbed 强调轻量、基于 ONNX Runtime、无需 GPU，适合本地 MVP。Ollama 官方仓库使用 MIT 许可证。当前已锁定并安装 qdrant-client 1.18.0、fastembed 0.8.0，且已完成 FastEmbed+Qdrant 真实 smoke；模型许可证仍需与代码许可证分开核验。

## 仅参考，暂不引入

## 二次开发对比与借鉴边界

| 项目 | 原生强项 | DevMemo AI 借鉴 | 不直接采用的原因 |
|---|---|---|---|
| [Memos](https://github.com/usememos/memos) | MIT、轻量 Markdown 快速捕获、自托管 | 保持 upstream 兼容，把 AI 放在 Webhook/HTTP/adapter 外围 | 原项目核心应保持低复杂度，避免把 AI 逻辑塞进 Memos store |
| [Khoj](https://github.com/khoj-ai/khoj) | AGPL-3.0、个人 AI、语义搜索、agent 和自动化 | 借鉴“长期记忆”和主动回顾，落成可审核的 insight/decision ledger | 不复制 AGPL 源码，不引入其完整 agent/云端产品面 |
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) | MIT、workspace RAG、memory、agents、MCP、多文档和引用 | 借鉴 workspace context、来源可见和未来 Context Pack | 运行时面太大，包含 telemetry/agent/多 provider 维护成本；保持现有薄 adapter |
| [AFFiNE](https://github.com/toeverything/AFFiNE) | local-first 文档、画布、表格和知识工作区 | 借鉴“Memo + 结构化视图”的 UI 方向 | 许可证/子模块边界需逐项审计，不复制其工作区实现 |
| [Logseq](https://github.com/logseq/logseq) | AGPL-3.0、本地知识图谱、DB graph、时间线与插件 API | 借鉴本地关联、时间维度和可追溯来源 | 不复制 AGPL 代码；暂不引入图数据库，先用 SQLite 派生关系 |
| [Outline](https://github.com/outline/outline) | BSL 1.1、协作知识库、历史、权限和 MCP | 借鉴历史对比、来源 breadcrumbs 和协作审阅体验 | BSL 许可和团队协作复杂度不适合作为当前运行时依赖 |

### 推荐的创新定位

不要把 DevMemo AI 做成“缩小版 AnythingLLM”。建议形成 `Capture → Insight → Review → Recall → Context Pack` 闭环：

- Capture：保留 Memos 的低摩擦速记。
- Insight：从 Code/Bug/普通 Memo 提出带置信度的事实、决策、行动候选。
- Review：AI Inbox 中显式接受/拒绝，所有派生内容可撤销。
- Recall：按时间、状态、来源和 Memo 关联回看，识别过期/冲突候选。
- Context Pack：将已确认内容编译成有限预算、带来源的开发上下文，供人工复制到 IDE 或后续工具。

这条路线的护城河不是模型或向量库，而是“开发知识的 provenance + approval + temporal lifecycle”数据契约；它能复用当前项目已有的 deterministic/offline 边界，且不会把公共 chat 兼容性押在未批准的 chunk API 上。

### LiteLLM

LiteLLM 可以统一多家 LLM API、做路由、成本和日志，但会增加网关、密钥管理和升级面。当前只有 OpenAI/Ollama 两个后端，现有薄适配器更容易测试和回滚，因此暂不引入。

未来若需要多租户、fallback 或预算限制，再单独评估 LiteLLM；必须锁定已修复安全问题的版本并运行漏洞扫描，不使用 `latest` 镜像。

### LangChain / LlamaIndex

当前 RAG 只需要分块、向量 upsert、相似度查询、上下文拼接，先用项目自己的小型接口保持可控；当出现 rerank、混合检索、评估器等复杂用例时再评估。

## 供应链门禁

- 新增运行时依赖记录用途、版本、许可证和替代方案。
- Python 依赖使用锁定文件；Docker 镜像从 `latest` 迁移到显式版本或 digest。
- 每个阶段执行依赖漏洞扫描和 SBOM 生成。
- 第三方模型的许可证与代码许可证分开核验。
