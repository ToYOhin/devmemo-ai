# 下一阶段 Prompt：Phase 4g 显式清理批准与审计边界

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
- Phase 4b/4c/4d：Webhook HMAC、SQLite outbox、幂等入队、有限显式 retry、max_attempts 和基础观测。
- Phase 4e：AI_OPS_TOKEN 保护 ops GET/retry；公开响应移除 payload，错误摘要单行且最多 240 字符。
- Phase 4f：retention preview 只读预览 processed/failed 终态；alerts 只读返回失败/耗尽摘要，不主动推送。
- 当前 AI Service 测试为 105 passed；默认 Compose 仍 deterministic + memory，没有后台 worker 或外部队列。

当前目标：实现 Phase 4g 的“显式清理批准与审计边界”最小垂直切片。

本次只做：
1. 先检查 retention-preview、alerts、AI_OPS_TOKEN 和 webhook_events 当前契约。
2. 如确有必要，新增两步式清理：先生成带 cutoff/candidate IDs 的 preview，再由显式 confirm/approval 请求删除；默认请求必须 dry-run 或拒绝执行。
3. 清理只能作用于 preview 中的 processed/failed 终态事件，必须再次校验 cutoff，不能删除 pending、超出 preview 的 ID 或用户 Memo 原文。
4. 在 AI Service 自有 SQLite 增加最小清理审计记录，至少保存执行时间、请求者标识摘要、删除数量和 cutoff；不得保存 ops secret。
5. 增加空库、未确认、ID 越界、pending 保护、重复执行幂等和审计查询测试。
6. 保持 AI_OPS_TOKEN、Webhook code=0、AI Service 默认 deterministic + memory、Qdrant/AI volume 和 Memos 核心不变。

不要做：
- 不默认删除数据，不使用 docker compose down -v，不删除 Qdrant/AI volume。
- 不修改 Memos server/store/proto/web 核心。
- 不启动 worker、定时任务、Redis、Celery、Prometheus 或前端运维 UI。
- 不删除 ai_notes、memo_templates、webhook_events 或原始 Markdown；清理只处理 AI outbox 派生记录。

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
- 清理无法通过 cutoff、状态和显式确认同时约束时，保留 preview-only，不直接实现删除。
- 审计需要保存 secret、引入外部服务或改变默认启动时保留兼容方案，不扩大范围。
~~~
