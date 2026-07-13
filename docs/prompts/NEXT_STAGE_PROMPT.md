# 下一阶段 Prompt：Phase 4d 显式重试与最小观测

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
- Phase 4b：可选 Webhook HMAC-SHA256；AI_WEBHOOK_SECRET 为空时保持旧 code=0 兼容。
- Phase 4c：AI Service SQLite webhook_events，eventId/body-hash 幂等入队、processed/failed 状态、attempts/last_error 和 GET /api/ai/ops/outbox。
- 当前 AI Service 测试为 95 passed；没有后台 worker、自动重试或外部队列。

当前目标：实现 Phase 4d 的“显式有限重试与最小观测”最小垂直切片。

本次只做：
1. 先检查 webhook_events 当前 schema、状态读取 API 和 code=0/HMAC 契约。
2. 只增加显式、有限次数的 retry API 或命令；默认不启动后台 worker，不自动无限重试。
3. 增加 max_attempts、retry_at 或等价字段前先做兼容 SQLite 补列，不能删除旧表和旧数据。
4. retry 只能针对 failed 事件，超过上限返回明确错误；成功后更新 processed、attempts、last_error/updated_at。
5. 增加最小观测：至少按 status 返回计数或最近错误摘要；不引入 Prometheus、Redis、Celery 或新的运行时依赖。
6. 保持 Webhook 默认 code=0、AI_WEBHOOK_SECRET 显式启用、默认 deterministic + memory。

不要做：
- 不修改 Memos server/store/proto/web 核心。
- 不实现常驻后台 worker、队列、分布式锁或无限重试。
- 不加入前端运维 UI、chunk/rerank、LangChain/LlamaIndex。
- 不删除 ai_notes、memo_templates、webhook_events 或原始 Markdown。

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
- SQLite 补列无法兼容现有数据库时先提出迁移方案，不删除旧表。
- 重试需要默认启动 worker、外部队列或改变 code=0 时保留显式 opt-in，不扩大范围。
~~~
