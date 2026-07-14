# 下一阶段 Prompt：Phase 5g Qdrant chunk rollout gate

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，不要同时操作 project4 下的其他 worktree。默认快速推进，允许一次完成一个完整垂直切片，但每个切片必须先测试并真实记录结果；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-14-single-agent-handoff.md
2. docs/PROJECT_STATUS.md
3. docs/HANDOFF.md 顶部当前阶段
4. 本文件
5. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 4/4b/4c/4d/4e/4f/4g、Phase 5a/5b/5c/5d/5e 已完成。
- Phase 5f 代码切片已完成：独立 QDRANT_CHUNK_COLLECTION/config/composition、ChunkRetrievalService 内部 contract 和 smoke 脚本均已落地。
- 默认完整 Memo 是 memo-v1 + deterministic + memory；只有 AI_INDEX_ON_WEBHOOK=true 且 AI_INDEX_MODE=chunk 才启用 chunk lifecycle。
- 显式 chunk + qdrant 使用独立 memo-chunk-v1 collection；公共 POST /api/ai/chat 继续只检索完整 Memo。
- ChunkRetrievalService 严格校验 memo_id、chunk_id、chunk_index、index_version、source_type 和 index_mode；content 只进入服务端 context，不进入 citation metadata。
- smoke 命令：
  cd H:\DevMemoAI\ai-service
  .\.venv\Scripts\python.exe -m scripts.smoke_qdrant --provider deterministic --mode chunk
- 当前真实 smoke 已通过：Docker Desktop/Qdrant 已恢复，`QDRANT_CHUNK_SMOKE_OK` 验证 health、重连持久性、内部 contract 和 delete；后续如环境重启再按同一命令复验。

本阶段目标：
1. Docker/Qdrant 可用时执行 deterministic chunk smoke，确认 health、point_count、重新连接后检索仍存在、内部 chunk contract 和 delete；临时 collection 自动清理，不删除 volume。
2. 执行完整验证门禁并核对文档事实；若 smoke 通过，补充真实版本/collection 清理证据；若阻塞，保留代码与 fake/offline contract，明确未验证项。
3. 评估 chunk retrieval 是否继续保持内部边界。没有新的兼容性证据时，不接入公共 chat、不改完整 Memo collection。

允许修改：AI Service adapters/services/tests、scripts/verify-devmemo.ps1 需要的最小验证接线、docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/handoffs/、docs/roadmap.md、docs/api.md、docs/structure.md、docs/DECISIONS.md 和本 Prompt。

禁止修改：Memos server/store/proto/web 核心；默认 AI_INDEX_ON_WEBHOOK=false、AI_INDEX_MODE=memo、AI_VECTOR_STORE=memory；公共 chat citation；不执行 docker compose down -v，不删除现有 collection 或 volume，不加入 rerank/BM25/混合检索/聊天 UI/LangChain/LlamaIndex/Redis/Celery/Prometheus/新默认依赖，不创建并行 Agent。

验证顺序：
- cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- docker compose config --quiet
- cd web; pnpm test; pnpm exec tsc --noEmit --skipLibCheck; pnpm build; pnpm lint
- 如 Docker 可用：运行上面的 deterministic chunk smoke；再按需运行 .\scripts\verify-devmemo.ps1 -FullBackend
- git diff --check

完成条件：
- smoke 结果、Docker 阻塞证据或通过证据真实写入 PROJECT_STATUS/HANDOFF/handoff/changelog。
- 所有代码和文档事实一致，公共 chat 没有回归。
- 形成一个清晰 commit；不 push。
- 最终报告测试结果、未验证项、阻塞证据、commit 和下一步。
~~~
