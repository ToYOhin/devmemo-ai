# 下一阶段 Prompt：Phase 4c Outbox、重试与观测

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
- Phase 4b：可选 Webhook HMAC-SHA256；AI_WEBHOOK_SECRET 为空时保持旧 code=0 兼容，配置后无效签名返回 401。
- 当前 AI Service 测试基线为 90 passed，HMAC 定向测试已通过。

当前目标：实现 Phase 4c 的“AI Service 自有 SQLite outbox、有限重试与最小观测”最小垂直切片。

本次只做：
1. 先检查现有 ai_notes/memo_templates SQLite 初始化边界和 Webhook 摘要/模板/索引失败路径。
2. 只在 AI Service 自有 SQLite 新增兼容 outbox 表，记录 event_id、event_type、payload、status、attempts、last_error、created_at、updated_at。
3. 首先覆盖 webhook event_id 幂等入队和失败状态读取；不要修改 Memos 数据库或核心 API。
4. 增加一个明确的 GET 运维读取 API 或最小命令，避免引入后台 worker、Redis、Celery 或新的依赖。
5. 保持 Webhook 默认 code=0；签名校验仍由 AI_WEBHOOK_SECRET 显式启用。
6. 增加不访问网络的 SQLite/API contract tests，保留默认 deterministic + memory。

不要做：
- 不修改 Memos server/store/proto/web 核心。
- 不加入 Redis、Celery、Kafka、LangChain/LlamaIndex。
- 不实现无限重试、后台常驻 worker、分布式锁或前端运维 UI。
- 不删除 ai_notes、memo_templates 或原始 Markdown。

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
- SQLite 迁移无法兼容现有 ai_notes/memo_templates 时先提出迁移方案，不删除旧表。
- 需要默认启动后台 worker、外部队列或外部服务时保留显式 opt-in，不扩大范围。
~~~
