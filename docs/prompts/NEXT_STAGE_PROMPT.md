# 下一阶段 Prompt：Phase 6 public chunk retrieval compatibility decision

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，不要同时操作 project4 下的其他 worktree。默认快速推进；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-14-single-agent-handoff.md
2. docs/PROJECT_STATUS.md
3. docs/HANDOFF.md 顶部当前阶段
4. 本文件
5. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 5f/5g 已完成：独立 QDRANT_CHUNK_COLLECTION、ChunkRetrievalService 内部 contract、真实 Qdrant health/persistence smoke 和完整验证门禁均通过。
- 最新真实 smoke：`QDRANT_CHUNK_SMOKE_OK`；初始/重连 point_count=2，删除后为 1，临时 collection 已清理；Qdrant Server 1.18.2。
- AI Service 153 passed；前端 131 passed；TypeScript、build、lint、Compose config 和 Go `go test -p 2 ./...` 通过。
- 默认完整 Memo 是 memo-v1 + deterministic + memory；显式 chunk + qdrant 才使用独立 memo-chunk-v1 collection。
- 公共 `POST /api/ai/chat` 继续只检索完整 Memo；chunk retrieval 当前刻意保持内部边界。

本阶段目标：
1. 只评估 public chunk retrieval 是否有兼容、安全、排序、引用和迁移/回滚条件，不直接改变公共 chat。
2. 对比现有完整 Memo `Citation` 与内部 `ChunkCitation`，明确一个未来公共响应是否需要新版本/新 endpoint；不要把 content 放入公共 metadata。
3. 若实现一个最小决策/contract 文档或离线评估，必须先写测试；若缺少明确兼容要求，停留在 ADR/评估边界，不新增 HTTP 行为。

允许修改：AI Service provider-neutral tests/services、离线评估、docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/handoffs/、docs/roadmap.md、docs/api.md、docs/structure.md、docs/DECISIONS.md 和本 Prompt。

禁止修改：Memos server/store/proto/web 核心；默认 AI_INDEX_ON_WEBHOOK=false、AI_INDEX_MODE=memo、AI_VECTOR_STORE=memory；公共 chat citation 和完整 Memo collection；不执行 docker compose down -v，不删除现有 collection 或 volume，不加入 rerank/BM25/混合检索/聊天 UI/LangChain/LlamaIndex/Redis/Celery/Prometheus/新默认依赖，不创建并行 Agent。

验证顺序：
- cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- docker compose config --quiet
- cd web; pnpm test; pnpm exec tsc --noEmit --skipLibCheck; pnpm build; pnpm lint
- 如涉及 Qdrant adapter/lifecycle，运行 deterministic chunk smoke
- 如环境允许，运行 .\scripts\verify-devmemo.ps1 -FullBackend；Go 全量可能需要较长时间
- git diff --check

完成条件：
- 明确记录 chunk 是否继续内部边界，或提出带版本/迁移/回滚的公共契约。
- 所有测试、未验证项和边界事实写入 PROJECT_STATUS/HANDOFF/handoff/changelog。
- 形成一个清晰 commit；不 push。
- 最终报告测试结果、未验证项、commit 和下一步。
~~~
