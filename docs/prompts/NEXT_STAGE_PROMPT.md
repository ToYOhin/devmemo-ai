# 下一阶段 Prompt：Phase 4b 索引可靠性与 Webhook 运维边界

将下面整段复制到新的 Codex 窗口或下一次任务中：

~~~text
你正在继续 H:\DevMemoAI 的 DevMemo AI 项目。

先读取以下真相源：
- docs/PROJECT_STATUS.md
- docs/HANDOFF.md
- docs/roadmap.md
- docs/structure.md
- docs/DOC_UPDATE_POLICY.md
- docs/DECISIONS.md
- docs/api.md
- docs/oss-adoption.md
- git status --short --branch
- git log --oneline -8

当前已完成：
- Phase 4 RAG 最小切片已完成：RetrievalService 执行问题 embedding、VectorStore.search 和引用上下文组装。
- POST /api/ai/chat 已提供，返回 answer、citations、provider、retrieved_count。
- 当前检索一个完整 Memo；索引派生 metadata 保存内部 content，公共 citations 会剥离 content。
- 默认 deterministic + memory 可离线运行；OpenAI/Ollama 复用现有 adapter；AI Service 当前 79 passed。

当前目标：实现 Phase 4b 的“索引可靠性与 Webhook 运维边界”最小垂直切片。

本次只做：
1. 先检查 Webhook 当前 code=0 降级、AI_INDEX_ON_WEBHOOK、chat/retrieval 错误边界。
2. 选择一个最小可靠性切片：Webhook HMAC 签名验证，或 AI Service 自有 SQLite outbox + 可重试状态；先说明选择理由。
3. 保持 provider-neutral，不让 FastAPI、qdrant-client、httpx 类型泄漏到 domain。
4. 增加不访问网络的 contract tests，并保持默认 deterministic + memory。
5. 不改变 Memos 核心 API、数据库、Proto、前端聊天 UI、chunk/rerank。
6. 更新所有真相源文档和下一个 Prompt，形成独立 commit。

验证命令：
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests
- docker compose config --quiet
- cd web; pnpm test
- cd web; pnpm exec tsc --noEmit --skipLibCheck
- cd web; pnpm build
- git diff --check

停止条件：
- 需要修改 Memos 核心 API、数据库或 Proto 时先停下报告影响。
- 需要默认启动外部服务、下载模型或引入 LangChain/LlamaIndex 时保留现状并报告。
- 可靠性方案会改变既有 Webhook code=0 契约时，先提出兼容方案，不直接破坏旧客户端。
~~~
