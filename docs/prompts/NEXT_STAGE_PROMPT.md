# 下一阶段 Prompt：Phase 4e 运维 API 安全与告警边界

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
- Phase 4c：AI Service SQLite webhook_events，eventId/body-hash 幂等入队、processed/failed 状态和 GET /api/ai/ops/outbox。
- Phase 4d：兼容补充 max_attempts，新增 POST /api/ai/ops/outbox/{event_id}/retry；默认总尝试上限 3，并返回 by_status/recent_errors。
- 当前 AI Service 测试为 100 passed；默认 Compose 仍为 deterministic + memory，没有后台 worker 或外部队列。

当前目标：实现 Phase 4e 的“运维 API 安全与告警边界”最小垂直切片。

本次只做：
1. 先检查 `/api/ai/ops/outbox` 及 retry API 当前认证、payload 暴露和错误摘要边界。
2. 增加显式可选的 ops 访问令牌或等价来源限制；未配置时保持本地开发兼容，配置后 GET/retry 都必须通过校验。
3. 评估并最小化 outbox payload 和 last_error 的敏感信息暴露；保留排障所需 event_id、状态、attempts 和截断错误摘要。
4. 为认证成功/失败、默认兼容、错误摘要截断增加不访问网络的 API tests。
5. 保持 Webhook HMAC、原有 Webhook code=0、有限 retry 上限和默认 deterministic + memory。
6. 只记录基础安全/告警决策，不引入 Prometheus、Redis、Celery、后台 worker 或前端运维 UI。

不要做：
- 不修改 Memos server/store/proto/web 核心。
- 不实现常驻后台 worker、自动无限重试、外部队列或分布式锁。
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
- 认证方案会破坏默认本地 Webhook 或 code=0 时先提出兼容方案，不直接改变旧客户端。
- 需要默认启动外部服务、worker、队列或新增运行时依赖时保留显式 opt-in，不扩大范围。
~~~
