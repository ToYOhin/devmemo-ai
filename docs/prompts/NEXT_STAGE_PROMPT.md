# 下一阶段 Prompt：Phase 5 检索质量增强

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
- Phase 4 RAG：RetrievalService 和 POST /api/ai/chat，默认 deterministic + memory。
- Phase 4b/4c/4d/4e：Webhook HMAC、SQLite outbox、幂等入队、有限 retry、ops token 和错误脱敏。
- Phase 4f：retention preview、alerts 只读轮询。
- Phase 4g：显式 dry-run/confirm 清理、cutoff/preview 集合二次校验、pending 保护、approval_id 幂等和 cleanup audit。
- 当前 AI Service 测试为 108 passed；默认 Compose 仍 deterministic + memory，没有后台 worker 或外部队列。

当前目标：实现 Phase 5 的“检索质量增强”最小可验证切片，优先选择 Memo chunking 或检索评估边界中的一个，不同时扩大范围。

本次只做：
1. 先检查当前完整 Memo 索引、RetrievalService、VectorStore metadata 和 POST /api/ai/chat 契约。
2. 选择一个最小切片并说明理由：建议先做 provider-neutral Memo chunking + 稳定 chunk ID，或先做离线检索评估 fixture。
3. 保持现有完整 Memo 索引和 chat API 兼容；必要时使用 index_version/mode 进行显式区分。
4. 增加不访问网络的 unit/contract tests，默认 deterministic + memory 继续低 CPU、可离线运行。
5. 不修改 Memos server/store/proto/web 核心，不删除既有向量、AI SQLite 数据或原始 Markdown。

不要做：
- 不同时加入 chunk、rerank、混合检索、聊天 UI、流式输出和评估平台。
- 不引入 LangChain、LlamaIndex、Redis、Celery、Prometheus 或新的默认运行时依赖。
- 不改变 Webhook code=0、AI_OPS_TOKEN、清理审批/审计和默认 Compose 启动契约。
- 不让 FastEmbed、Qdrant 或 FastAPI 类型泄漏到 domain。

验证命令：
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests
- docker compose config --quiet
- cd web; pnpm test
- cd web; pnpm exec tsc --noEmit --skipLibCheck
- cd web; pnpm build
- git diff --check

完成条件：
- 选定的 Phase 5 小切片有清晰 provider-neutral 边界和 contract tests。
- 原有 AI Service 108 个测试、前端 131 个测试、Go 全量和 Docker 配置不回归。
- 更新 docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/roadmap.md、docs/api.md、docs/structure.md、docs/DECISIONS.md。
- 更新本文件和 docs/prompts/NEW_WINDOW_PROMPT.md 的默认阶段描述。
- 形成独立 commit，报告真实验证结果、未验证项、阻塞证据和下一阶段 Prompt。

停止条件：
- 需要修改 Memos 核心 API、数据库或 Proto 时先停下报告影响。
- 需要下载模型或访问外部服务才能验证时，先保留 fake/offline 路线并记录证据。
- 如果 chunking 会破坏现有完整 Memo 索引或 citation 契约，先只做评估 fixture，不直接替换索引。
~~~
