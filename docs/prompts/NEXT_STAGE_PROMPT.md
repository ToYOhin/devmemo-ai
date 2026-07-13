# 下一阶段 Prompt：Phase 4f Outbox 保留与告警导出边界

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
- Phase 4c/4d：SQLite webhook_events、幂等入队、有限显式 retry、max_attempts 和 by_status/recent_errors。
- Phase 4e：可选 AI_OPS_TOKEN 保护 ops GET/retry POST；公开 outbox item 移除原始 payload；错误摘要单行且最多 240 字符。
- 当前 AI Service 测试为 102 passed；默认 Compose 仍 deterministic + memory，没有后台 worker 或外部队列。

当前目标：实现 Phase 4f 的“Outbox 保留与告警导出边界”最小垂直切片。

本次只做：
1. 先检查 webhook_events 当前 created_at/updated_at、max_attempts、ops token 和错误摘要契约。
2. 增加 AI Service 自有 SQLite 的显式、可控保留策略或只读清理预览；默认不自动删除数据，必须显式 opt-in。
3. 增加最小告警导出契约，例如只读 JSON 摘要/命令输出；只暴露 event_id、status、attempts、max_attempts 和已截断错误，不返回 payload 或 secret。
4. 保持 AI_OPS_TOKEN 保护新 ops API，未配置时继续本地兼容；增加保留边界、空库、错误脱敏和权限测试。
5. 不引入 Prometheus、Redis、Celery、后台 worker、定时任务或前端运维 UI。

不要做：
- 不修改 Memos server/store/proto/web 核心。
- 不执行默认数据删除，不使用 docker compose down -v，不删除 Qdrant/AI volume。
- 不把 AI Service SQLite 暴露给 React，不新增 LangChain/LlamaIndex。
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
- 保留策略会默认删除用户数据、改变旧 SQLite 表或影响 Qdrant volume 时先提出迁移/预览方案。
- 告警导出需要默认外部服务、worker、队列或新运行时依赖时保留显式 opt-in，不扩大范围。
~~~
