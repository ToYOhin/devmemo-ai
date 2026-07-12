# 开源组件采用记录

| 组件 | 用途 | 决策 | 边界 |
|---|---|---|---|
| Memos | 原有笔记系统 | 保留上游 `v0.29.1` | 不复制源码，不把 AI 逻辑塞进 Store |
| Qdrant | 向量存储和过滤检索 | Phase 3 采用 | 只存派生索引，collection 版本化 |
| qdrant-client | Python Qdrant SDK | Phase 3 采用 | 只允许出现在 `adapters/vectorstore` |
| FastEmbed | CPU/ONNX embedding | Phase 3 优先采用 | 锁定模型和维度，单独检查模型许可证 |
| Ollama | 本地 LLM runtime | 当前保留 | 通过 `LLMProvider`，不让业务依赖 Ollama API |
| FastAPI | AI Service HTTP 层 | 当前已采用 | 路由只负责协议转换和错误边界 |

Qdrant、qdrant-client 和 FastEmbed 官方仓库为 Apache-2.0；FastEmbed 强调轻量、基于 ONNX Runtime、无需 GPU，适合本地 MVP。Ollama 官方仓库使用 MIT 许可证。采用前仍需按具体版本复核依赖和模型许可证。

## 仅参考，暂不引入

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
