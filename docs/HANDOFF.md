# DevMemo AI 当前交接

## Phase 10 DevMemory feedback observation boundary (2026-07-20)

- Route B did not create synthetic feedback. An authenticated Chrome session showed one existing local Bug Report capture, while the configured read-only AI SQLite lifecycle report had `memo_insights=0`. A second read-only check rendered the expected empty `/inbox` page, so the earlier retained Memo body is not treated as a product defect.
- Focused regression passed: MemoInsight, Context Pack builder/golden, and lifecycle-report tests (`15 passed`). Memos rejected unauthenticated `auth/me` with `401`; Compose and AI health were up.
- AI Service full suite and `scripts/verify-devmemo.ps1` passed with `187 passed`; Compose config passed. Fresh Web test/build/lint were intentionally not rerun after this documentation-only slice at the user's CPU-conservation request; strict TypeScript still has the known 13 baseline declaration errors.
- No accept/reject, delete/revoke, budget/copy action, human feedback, or persistent mutation was observed. Treat [`docs/handoffs/2026-07-20-devmemory-feedback-observation.md`](handoffs/2026-07-20-devmemory-feedback-observation.md) as the authority for this incomplete evidence, not as a product-feedback pass.
- Route B next slice is now planned in [`docs/handoffs/2026-07-20-devmemory-real-feedback-plan.md`](handoffs/2026-07-20-devmemory-real-feedback-plan.md): one stable authenticated session and a real consenting participant, with safe-only evidence and explicit stop conditions. Keep `AI_PUBLIC_CHUNK_RETRIEVAL=false` and do not alter public chat, Memos core, collections, or volumes.

## Phase 10 local gateway contract evidence (2026-07-20)

- `ai-service/scripts/public_chunk_gateway_contract_smoke.py` uses an in-process TestClient as a trusted-gateway simulator. It covers exact raw-body HMAC, tampered-body `401`, duplicate scope `422`, disabled/degraded `503`, and authorized, deduplicated, redacted `200` responses.
- Full verification: AI Service `187 passed`; Web `33 files / 149 passed`, build, and project `pnpm lint` passed. Standalone strict `pnpm exec tsc --noEmit` remains blocked by 13 pre-existing dependency declaration and `src/types/view.d.ts` errors; the project lint TypeScript command uses `--skipLibCheck` and passed.
- It does not start a service, contact a network, or output its temporary secret. This is local contract-only evidence, not a real gateway/deployment/canary rollout pass. Keep `AI_PUBLIC_CHUNK_RETRIEVAL=false` by default.
- Next slice: either verify a real trusted gateway with permission mapping and rollback conditions, or record one Bug Report DevMemory Loop feedback path. Do not change public chat, Memos core, collections, or volumes.

## 当前权威快照（2026-07-20）

- 先读取 [`docs/handoffs/2026-07-20-devmemory-rollout-handoff.md`](handoffs/2026-07-20-devmemory-rollout-handoff.md)；它取代下方历史阶段叙述作为新窗口入口。
- Phase 9f 的跨语言 Context Pack golden、SQLite 只读生命周期诊断和真实 Chrome/Windows 系统剪贴板验收已完成。`Copy Markdown`、`Copy JSON` 都实际写入了系统剪贴板，且复制后无 React error boundary。
- 当前分支仍只允许单 Agent 在 `H:\DevMemoAI` 主工作树推进。默认路径保持 deterministic + memory；`public-chunk-v1` 默认关闭，公共 chat 与 Memos 核心不改。
- 结构检查结论：Memos Go 是原始 Memo/权限事实源，AI Service 只管理派生状态，Web 的 `AiMemoInsights`/`AiMemoContextPack` 是唯一当前产品入口；`graphify-out` 未覆盖近期 AI feature，不能单独作为当前结构事实源。

## Phase 8 public-chunk-v1 controlled implementation (2026-07-20)

- Public `POST /api/ai/v1/chunks/search` now exists behind `AI_PUBLIC_CHUNK_RETRIEVAL=false`. It requires a non-empty `AI_PUBLIC_CHUNK_SECRET` and `X-DevMemo-Chunk-Signature` HMAC over the raw JSON body; the signed, unique `visible_memo_ids` are the gateway-provided authorization scope.
- The response is an independent `public-chunk-v1` contract: fixed `memo-chunk-v1`, deterministic sort, highest score per authorized Memo, and redacted metadata allowlist only. It never returns content, raw webhook payloads, secrets, or unapproved internal metadata.
- Rollback: disable the flag; do not delete collections/volumes or alter `/api/ai/chat`. Targeted public API/contract/chat tests passed 13; AI full suite passed 186; controlled delete/replay/reject/stale/accepted-only evidence passed 11.
- Real Chrome clipboard proof has since passed; see the current snapshot above.

## Phase 9f minimum slice: golden parity and local diagnostic (2026-07-20)

- `contracts/context-pack-v1.json` now supplies shared expected Markdown and canonical compact snake_case JSON golden output. Python and Web have independent implementations but exact output tests prevent contract drift; the test caught and fixed a Web trailing-newline mismatch.
- `ai-service/lifecycle_report.py` plus `python -m scripts.devmemory_lifecycle_report [--database <path>]` is a local read-only diagnostic. It opens SQLite with `mode=ro`, reports only aggregate AI-derived table/status/version counts, does not create/migrate/write a DB, and never emits memo IDs, content, raw webhook payloads, or secrets.
- Current evidence: AI full `179 passed` with one existing Starlette/httpx deprecation warning; Web full `33 files / 149 passed`; verify script, Compose config, TypeScript, build, lint, and `git diff --check` passed.
- The previously outstanding real Chrome system-clipboard acceptance is now complete. Public chat, Qdrant collections, and the default-disabled Phase 8 rollout boundary are unchanged.

## 人工验收与问题修复（2026-07-15）

- 已手动验证创建两条 Memo、AI Inbox Accept/Reject、Context Pack question/预算、accepted-only 和显式跨 Memo 选择；本轮稳定详情页截图已在工具结果中展示。
- 修复 `memos/{uid}` 与详情路由 `{uid}` 混用导致的当前 Memo 重复来源；修复取消全部来源后无法重新勾选的问题。
- 删除 Memo 的 AI 派生状态清理补齐 `memo_chunk_index_state`；chunk mode 先删除向量/生命周期再清理 SQLite，避免提前删状态导致 `index_status=skipped`，并增加 webhook 回归测试。
- 复制验收发现当前 In-App Browser 禁用 `navigator.clipboard` 和 `document.execCommand`；现已改为选中预览并显示 `Ctrl+C` 手动复制提示，不再显示误导性的 copy failure。刷新最新前端后的详情页 DOM 已确认提示可见；真实 Chrome/用户浏览器的系统剪贴板仍需单独复验。本轮 CDP 截图调用超时，既有稳定详情页截图仍有效。Statsig 外部请求超时与本地功能无关。

## 人工功能检查修复（2026-07-14）

- 已修复本地回环地址 CORS 缺口：Compose 默认同时允许 `localhost:3001` 与 `127.0.0.1:3001`。
- 已记录源码变更后使用 `docker compose up -d --build`，避免 AI Service 复用旧镜像。
- `POST /api/ai/summarize` 现在会为显式 Code Snippet/Bug Report 持久化详情页模板；Memo 保存后的自动处理仍需要配置 Memos Webhook。

## Phase 9a DevMemory Loop 首个切片已完成

- 已落地 provider-neutral `MemoInsight` contract、deterministic 候选提取、AI SQLite 幂等表，以及 preview/查询/approve/reject 内部 API。
- Memo 详情页已接入 AI Inbox 卡片，支持 pending 状态人工确认/拒绝、空态、失败态和来源引用；过期版本更新返回 409。
- 验证：AI Service `162 passed`；前端 `136 passed`；TypeScript、build、lint 通过；Compose API Bug Report smoke 生成 bug/action 并成功批准；Playwright 截图 artifact：`devmemo-phase9-ai-inbox.png`。
- 该路线不依赖 Phase 8 public chunk API 批准；不修改公共 chat、完整 Memo collection、chunk collection 或默认 deterministic + memory。Context Pack 仍只定义 contract/fixture，不实现 agent、网页搜索或 MCP。
- 下一阶段执行 [`docs/prompts/NEXT_STAGE_PROMPT.md`](prompts/NEXT_STAGE_PROMPT.md) 的 Phase 9b Context Pack contract。

## Phase 9b Context Pack contract 已完成

- 新增 provider-neutral `ContextPackRequest`、`ContextPackMemo`、`ContextPackItem`、`ContextPackSource` 和 `ContextPackResponse`，版本固定为 `context-pack-v1`。
- `build_context_pack` 只消费显式 Memo IDs、显式 accepted insight IDs 和安全 title/summary；未知 ID、pending/rejected、insight 未显式选择其 Memo、空/超限预算都会被拒绝或显式截断。
- 输出包含 bounded Markdown、稳定 JSON、去重 source 列表、confidence/updated_at/稳定 ID 排序和 `max_chars`/`max_items` 截断原因；未新增 HTTP、Qdrant 或公共 chat 行为。
- 验证：Context Pack 定向 12 passed；AI Service 全量 `174 passed`，保留 1 个 Starlette/httpx 弃用警告；示例输出由 `context-pack-v1` fixture 覆盖。
- 下一阶段执行 [`docs/prompts/NEXT_STAGE_PROMPT.md`](prompts/NEXT_STAGE_PROMPT.md) 的 Phase 9c Context Pack integration gate，先等待产品入口/权限边界决策。

## Phase 9d Context Pack internal preview/copy 已完成

- 用户已明确批准 Memo 详情页 AI Inbox 内部 preview/copy 入口。
- 新增 `web/src/features/ai/AiMemoContextPack.tsx` 与 `web/src/features/ai/contextPack.ts`：默认选择当前 Memo 与所有 accepted insights；来源可逐项取消；当前 slice 不加载其他 Memo，因此不存在隐式跨 Memo 扩展。
- question、`max_chars`、`max_items`、Markdown preview、Markdown 主复制、JSON 可选复制、sources、截断原因、empty/error/copy-error 状态均已接入；pack 只存在 React 内存，不写 SQLite、不新增 HTTP、不读 Qdrant。
- `web/tests/ai-context-pack.test.ts` 与 `web/tests/ai-context-pack.test.tsx` 覆盖 contract、accepted-only、显式选择、预算截断、空/失败/复制失败和不暴露原文；全前端 `143 passed`。
- Playwright 手动路径：登录 -> 打开 `/memos/LFodC7kD9ydf36MPSxT4sN` -> AI Inbox 点击 Accept -> Context Pack 输入 question -> 调整预算 -> Copy Markdown/JSON；390x844 已验证窄屏换行。截图 artifact：`devmemo-phase9d-context-pack-desktop.png`、`devmemo-phase9d-context-pack-mobile.png`。
- AI Service 查询错误作为不可见/删除 Memo 的 failure 边界；pending/rejected/撤销或过期 insight 不进入 pack。当前没有跨 Memo picker、删除事件清理或 pack 审计持久化，这些留给下一阶段产品决策。

## Phase 9e 共享 fixture、权限感知跨 Memo 选择、删除/撤销联动已完成

- 新增根目录 [`contracts/context-pack-v1.json`](../contracts/context-pack-v1.json)，Python `ai-service/tests/context_pack_fixture.py` 与 Web contract test 共同读取，覆盖同一 Memo/insight、accepted/pending、source_refs 和安全摘要样例；生产 builder/adapter 不读取 fixture。
- `AiMemoContextPack` 使用 Memos 当前用户可见的 `useInfiniteMemos({ pageSize: 50 })` 生成可选 Memo 列表；默认只勾选当前 Memo，跨 Memo 必须用户显式勾选，insight 通过同一 AI query key 读取并只纳入 accepted 状态。不可用的额外 insight 显示提示并被排除，当前 Memo 查询失败显示 failure。
- Memos deleted Webhook 现在无论索引是否开启都会调用 `delete_memo_ai_state`，清理 AI Service 自有 `ai_notes`、`memo_templates`、`memo_insights`、`memo_chunk_index_state`；chunk/vector 删除仍走原有显式索引路径，不删除 Memos 数据库、原文或 Qdrant volume。
- reject 是当前撤销语义：状态更新递增版本并失效同一 `aiInsightKeys.detail(memo_id)`，Context Pack 下一次构建只保留 accepted；stale version 仍返回 409。
- 本切片没有新增公共 HTTP、SQLite Context Pack 持久化、Qdrant 读取、Agent/worker 或 public chunk API；Phase 8 gate 继续 pending approval。

### Phase 9e 验证

- AI Service webhook 定向：8 passed；Context Pack 定向：12 passed。
- Web 全量：33 files / 147 passed；TypeScript、build、lint 通过；共享 fixture Web contract 已实际读取根目录 JSON，并覆盖不可访问跨 Memo 排除。
- AI Service 全量：175 passed，保留 1 个 Starlette/httpx 弃用警告；前端全量 147 passed；verify 脚本返回 `DEVMEMO_VERIFY_OK`；Compose config 与 `git diff --check` 通过。本段记录的是当时受限 In-App Browser 的手动复制结果；后续真实 Chrome/Windows 系统剪贴板验收已完成，以本文件顶部当前快照为准。

## 当前项目结构与问题

- Memos Go (`server/store/proto/internal`) 仍是原始 Memo 与权限事实源；AI Service (`ai-service/app`) 只保存 AI 派生状态；Web (`web/src/features/ai`) 是现有产品边界。
- AI Inbox 目前嵌入 Memo 详情页，不是全局收件箱；Context Pack 已有共享输入 fixture，但 Python builder 与 Web adapter 仍是两份实现，后续需继续用跨语言 contract 输出样例防止排序/预算语义漂移。
- `graphify-out` 的旧图把 “Inbox” 指向 Memos `store/inbox.go`，没有反映 Phase 9a/9d 的 AI feature；后续应重建图或改用精确节点查询。

验证与下一步：本段为 Phase 9e 历史记录；后续 Phase 9f golden、生命周期诊断和真实 Chrome 剪贴板验收已完成，Phase 8 也已实现默认关闭的受控路由。以本文件顶部当前快照为准。

## Phase 9c Context Pack integration gate：proposal-only 已完成

- 当前没有明确产品入口批准，因此不修改运行时 UI/API；Phase 9b builder、公共 chat、Qdrant 和 Memos 核心均保持不变。
- 推荐入口：Memo 详情页 AI Inbox 内的“复制 Context Pack”，默认只带当前 Memo；跨 Memo 必须由用户显式选择。命令面板和独立页面暂不采用。
- 权限/撤销边界：只允许当前用户可见 Memo 和 accepted insight；pending/rejected、删除 Memo、撤销 insight、过期版本和不可见来源必须排除；pack 不落库。
- 交互提案：Markdown 主复制格式，JSON 可选；展示 question、Memo/insight 选择、`max_chars`/`max_items`、sources、截断提示、空态、失败态和窄屏行为；不展示原始 content、Webhook payload、secret 或 chunk content。
- 以上是 Phase 9c 的历史 proposal-only 记录；入口现已获批准并由 Phase 9d 完成。下一步执行 [`docs/prompts/NEXT_STAGE_PROMPT.md`](prompts/NEXT_STAGE_PROMPT.md) 的 Phase 9e product acceptance slice。

## 2026-07-14 单 Agent 模式切换

## 2026-07-14 Phase 8 public chunk API implementation gate pending approval

- 新增 `QDRANT_CHUNK_COLLECTION`，默认 `devmemo_memo_chunks`，并由 Compose 透传。
- 配置拒绝空 chunk collection 名称或与完整 Memo `QDRANT_COLLECTION` 重合；fake Qdrant contract 校验独立 collection 的维度和 Cosine distance。
- 组合根已接入 chunk store 选择：仅 `AI_INDEX_MODE=chunk` + `AI_VECTOR_STORE=qdrant` 使用 `QDRANT_CHUNK_COLLECTION`，其他路径继续使用独立 memory store。
- chunk health 读取所选 store；默认完整 Memo、Webhook `code=0` 和 `/api/ai/chat` 不变。
- 新增内部 `ChunkRetrievalService`/`ChunkCitation`/`ChunkRetrievalResult`，严格校验 chunk metadata，原文不进入 citation metadata；公共 `/api/ai/chat` 未改变。
- `scripts/smoke_qdrant.py --mode chunk` 已覆盖 health、重新连接 persistence、内部 retrieval contract 和 delete；显式 collection 默认不自动删除。
- 聚焦测试：24 passed；Docker Desktop/Qdrant 恢复后真实 chunk smoke 已通过：`QDRANT_CHUNK_SMOKE_OK`，初始/重连 point_count=2，删除后 point_count=1，临时 collection 已清理。
- 完整门禁已通过：AI Service 153 passed；前端 131 passed；TypeScript/build/lint、Compose config 和 Go `go test -p 2 ./...` 通过，`store/test` 用时 168.864s；Qdrant Server 1.18.2。
- rollout gate 结论：chunk retrieval 继续保持内部边界，不接入公共 `/api/ai/chat`，不修改完整 Memo collection。
- Phase 6 决策：现有公共 `embedding_id`/`retrieved_count` 继续表示完整 Memo；不启用隐式 chunk mode，不新增未定义公共 chunk endpoint。未来公开 chunk retrieval 必须先有版本化 schema、Memo 去重/排序、content 脱敏和迁移/回滚测试。
- Phase 7 提案：未来独立 `POST /api/ai/v1/chunks/search` / `public-chunk-v1`，默认关闭；固定 `memo-chunk-v1`，同 Memo 只保留最高分 chunk，使用确定性排序和脱敏 metadata。本阶段未新增路由或运行时代码。
- Phase 8 gate：当前没有明确产品/兼容批准，故不实现 proposal endpoint、不新增 feature flag 运行时行为、不启动灰度；等待批准后再执行实现。

后续项目推进统一回到单 Agent：只使用 `H:\DevMemoAI` 主工作树，不启动 Terra/Luna 并行开发，不让多个 worktree 同时修改当前阶段。`project4` 下的多 Agent worktree 保留为历史/回滚参考，当前不作为开发入口。

详细接管快照见 [`docs/handoffs/2026-07-14-single-agent-handoff.md`](handoffs/2026-07-14-single-agent-handoff.md)。当前 HEAD 已包含 Phase 9a/9b 本地 commit，本轮尚未 push；工作区仍保留用户已有的 `docs/prompts/NEW_WINDOW_PROMPT.md` 未提交修改。

下一窗口先读取该快照和本文件顶部 Phase 9d 完成事实；继续保持 Phase 8 gate pending approval，执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 9e product acceptance slice。

## 2026-07-14 Phase 5e

Phase 5e 已完成 chunk health/status 最小切片：

- 新增 `ChunkIndexStateStats`、`ChunkIndexHealth` 和 GET `/api/ai/index/chunk-health`，返回 `memo-chunk-v1`、向量点数、tracked Memo/chunk 数、state backend 和 degraded detail。
- health 只读，不触发索引、不读取原始 Markdown、不改变完整 Memo `/api/ai/index/health` 或 `/api/ai/chat`。
- 覆盖空状态、生命周期计数、版本隔离、SQLite 状态读取和 HTTP contract；AI Service 当前 144 passed。
- 下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5f Qdrant chunk 持久化与显式 chunk 检索。

## 2026-07-14 文档与结构同步

- 已按实际仓库目录刷新 `docs/structure.md`：Memos Go/React 核心、`web/src/features/ai/`、AI Service domain/services/adapters、SQLite、Webhook 和 Compose 均已列出。
- 已同步 `README_AI.md`、`docs/architecture.md`、`docs/development.md`、`docs/api.md` 和 `docs/oss-adoption.md`，修正 Phase 3c 旧描述、不存在的 `.env.example` 命令和过期 lint 阻塞记录。
- 本次仅更新文档，没有修改运行时代码；沿用 Phase 5d 的 AI Service 142 passed、前端 131 passed、Go 全量和 build/lint 验证结果。

## 2026-07-14 Phase 5d

Phase 5d 已完成显式 chunk 索引生命周期：

- 新增 `ChunkLifecycleCoordinator`，`AI_INDEX_ON_WEBHOOK=true` 且 `AI_INDEX_MODE=chunk` 时处理 create/update/delete；默认仍使用完整 Memo `memo-v1`。
- 更新先 upsert 当前 `memo-chunk-v1` chunk，再删除旧尾部；空内容和删除事件清理已登记 chunk，eventId 重复事件继续由 outbox 幂等忽略。
- AI Service 自有 SQLite 新增 `memo_chunk_index_state`，记录版本和 chunk ID 列表，缺失状态不扫描向量库，不误删其他版本。
- chunk coordinator 使用独立 InMemoryVectorStore，避免 chunk 向量污染完整 Memo chat 检索；Qdrant chunk collection 尚未接入。
- chunk 失败保持 Webhook `code=0` 并返回 `index_status=failed`；公共 `POST /api/ai/chat` 完整 Memo citation 不变。
- AI Service 全量 142 passed；下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5e chunk 检索与可观测性收敛。

## 2026-07-13 Phase 5c

Phase 5c 已完成 chunk 离线检索评估：

- 新增 `OfflineChunkIndex`，用现有 deterministic provider 和 InMemoryVectorStore 构造独立试验索引；chunk ID 作为 embedding ID。
- 复用 `RetrievalService` 和 Phase 5a `RetrievalEvaluator`，可将完整 Memo 与 chunk 结果按 Recall@K/首个命中排名对照。
- chunk citation metadata 明确包含 `memo_id`、`chunk_id`、`chunk_index`、`index_version`；服务端上下文仍保留 chunk 原文，公共 chat API 不变。
- 更新、重复 ID、空内容和显式 stale delete 有 contract tests；没有接入 Webhook、Qdrant、FastEmbed、Compose 或 Memos 核心。
- AI Service 全量 133 passed；下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5d 可选 chunk 索引生命周期。

## 2026-07-13 Phase 5b

Phase 5b 已完成 Memo chunking 纯函数/内存边界：

- 新增 provider-neutral `MemoChunk` 与 `chunk_memo`，按换行边界和字符上限切分，拼接 chunk 内容可还原原始 Markdown。
- chunk ID 由 Memo ID、`index_version` 和位置稳定派生；metadata 使用 `memo-chunk-v1`/`index_mode=chunk`，与现有 `memo-v1` 完整 Memo 索引隔离。
- 更新时同位置复用 ID，内容缩短时通过旧 chunk 数量计算 stale IDs，供未来显式 delete；重复 ID 会在生命周期边界被拒绝。
- 本次没有接入 Webhook、Qdrant、FastEmbed、Compose 或 Memos 核心，也没有新增公共 HTTP API。
- AI Service 全量 129 passed；下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5c chunk 离线检索评估。

## 2026-07-13 Phase 5a

Phase 5a 已完成离线检索质量评估边界：

- 选择离线评估而不是直接切换 chunking，保护当前完整 Memo 索引和 citation 契约。
- 新增 `RetrievalEvaluationCase`、`RetrievalEvaluationResult` 和 `RetrievalEvaluator`，支持 Recall@K、命中列表、首个相关结果排名和批量评估。
- 评估器只依赖 provider-neutral `RetrievalService`，默认 deterministic + memory 可离线运行，不访问 FastEmbed/Qdrant。
- 没有新增公共 API，没有修改 Memos 核心、Webhook、outbox、AI SQLite 或向量存储。
- AI Service 全量 116 passed；下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5b Memo chunking 边界。

## 2026-07-13 Phase 4g

Phase 4g 已完成显式清理批准与审计边界：

- retention preview 返回 `cutoff`、`preview_limit` 和 `candidate_ids`，执行请求绑定同一预览集合。
- 新增 `POST /api/ai/ops/outbox/retention-cleanup`；默认 dry-run，必须 `confirm=true` 且 `dry_run=false` 才删除。
- SQLite 事务重新校验 cutoff、完整候选集合和终态；pending、越界 ID 或数据变化整批拒绝。
- 新增 cleanup audit 表和 `GET /api/ai/ops/outbox/cleanup-audits`；相同 approval_id 重复执行幂等，不保存 ops secret。
- 清理只作用于 AI Service 自有 webhook_events；AI Service 全量 108 passed。
- 下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5 检索质量增强。

## 2026-07-13 Phase 4f

Phase 4f 已完成 Outbox 保留预览与告警轮询边界：

- 新增受 `AI_OPS_TOKEN` 保护的 retention preview，按 `updated_at` 预览 30 天以上未更新的 `processed/failed` 事件，不删除、不影响 `pending`。
- 新增受保护的 alerts JSON 摘要，返回失败数、耗尽重试数和最多 5 条 warning/critical 摘要，不推送外部服务。
- 公开接口不返回 payload、secret 或未截断错误；没有启动 worker、队列、Prometheus，也没有修改 volume。
- AI Service 全量 105 passed；下一步执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 4g。

## 2026-07-13 Phase 4e

Phase 4e 已完成运维 API 安全与数据暴露边界：

- 可选 `AI_OPS_TOKEN` 通过 `X-DevMemo-Ops-Token` 保护 outbox GET 和 retry POST；未配置时保持本地兼容，错误令牌返回 401。
- 公开 outbox item 不返回原始 Webhook payload；SQLite 内部 payload 保留，retry 行为不变。
- `last_error` 和 `recent_errors` 摘要统一为单行、最多 240 字符；没有新增认证服务、Prometheus、worker 或队列。
- AI Service 全量 102 passed；下一步执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 4f。

## 2026-07-13 Phase 4d

Phase 4d 已完成显式有限重试与最小观测：

- `webhook_events` 兼容增加 `max_attempts`，默认每个事件最多 3 次总尝试，旧表和旧数据保留。
- 新增 `POST /api/ai/ops/outbox/{event_id}/retry`，只允许 `failed` 事件；达到上限返回 409。
- 重试成功清除 `last_error` 并转为 `processed`；重试失败仍返回 `code=0`，记录新的 attempts/error。
- GET outbox 增加 `by_status` 和最多 5 条 `recent_errors`；没有启动 worker、定时任务或外部队列。
- AI Service 全量 100 passed；下一步执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 4e。

## 2026-07-13 Phase 4c

Phase 4c 已完成 AI Service SQLite outbox 最小切片：

- `webhook_events` 以唯一 `event_id` 保存 event type、payload、pending/processed/failed、attempts 和 last_error。
- Webhook 优先入队；显式 `eventId` 优先，没有时使用原始 body hash；重复事件不重复执行旧业务流程。
- 处理异常仍返回 `code=0`，状态可通过 GET `/api/ai/ops/outbox` 查询。
- 没有启动 worker、自动重试或引入 Redis/Celery；下一阶段只做有上限的显式重试和最小观测。
- AI Service 全量 95 passed；Go、前端、TypeScript/build、Compose config 已通过。

## 2026-07-13 Phase 4b

Phase 4b 已完成可选 Webhook HMAC 最小切片：

- `app/services/webhook_security.py` 使用标准库 HMAC-SHA256 签名原始 body。
- `AI_WEBHOOK_SECRET` 为空时兼容旧客户端；配置后要求 `X-DevMemo-Signature: sha256=<hex>`，无效签名返回 401。
- 未修改 Memos 核心、SQLite schema、Qdrant、LLM 或前端；默认 Compose CPU/网络行为不变。
- HMAC/API 定向测试和 AI Service 全量 95 passed；Go、前端、TypeScript/build、Compose config 也已通过。

## 2026-07-13 Phase 4

Phase 4 RAG 最小切片已完成，新增 commit：

- `b9902a8`：provider-neutral retrieval service、完整 Memo 派生上下文和 retrieval tests。
- 当前工作区已接入 `POST /api/ai/chat`，本轮最终提交会同时包含 chat API、测试和真相源文档。

当前实现：

- `app/domain/retrieval.py` 只包含 Citation、RetrievalResult 和 provider-neutral 错误类型。
- `app/services/retrieval_service.py` 执行问题 embedding、VectorStore.search、引用和上下文组装，limit 范围为 1–10。
- `MemoIndexDocument` 将完整 Memo 原文保存为内部 `content` metadata；API citations 不返回该字段。
- `POST /api/ai/chat` 默认 deterministic + memory 离线运行；空库 200，检索不可用 503，LLM 失败 502。
- 当前 AI Service 全量测试为 79 passed；Phase 4 不包含 chunk、rerank 或前端聊天 UI。

Phase 4b、4c、4d 已在顶部交接记录；后续以 `docs/prompts/NEXT_STAGE_PROMPT.md` 为准。

## 2026-07-13 Phase 3g

Phase 3c/3d 已完成，代码 commits：

- c699400：FastEmbed adapter 和 fake/model contract tests
- 57732f9：AI_EMBEDDING_PROVIDER 配置、可选 requirements 和 Compose 环境变量
- 0c0d2cb：MemoIndexDocument/index_memo 索引边界
- 4a58e56：可选 Webhook 索引生命周期、稳定 upsert/delete 和失败降级
- 1f1f055：qdrant-client 安装后的测试兼容、真实 smoke 脚本和 Phase 3e 文档
- Phase 3f：Qdrant volume 重启验证、FastEmbed 缓存目录配置和文档同步
- Phase 3g：索引 health API、Qdrant 降级状态、FastEmbed 缓存错误提示和 Qdrant 镜像 digest 固定

## 继续工作前

~~~powershell
Set-Location H:\DevMemoAI
git status --short --branch
git log --oneline -8
.\scripts\verify-devmemo.ps1
~~~

## 当前实现

- app/adapters/qdrant_vector_store.py 只在显式 qdrant 模式下懒加载 qdrant-client。
- Qdrant adapter 使用 collection、VectorParams、PointStruct、PointIdsList 和 query_points。
- point payload 保存 embedding_id、memo_id、metadata；外部 VectorStore 类型不依赖 SDK。
- app/settings.py 读取 AI_VECTOR_STORE、QDRANT_URL、QDRANT_COLLECTION、QDRANT_API_KEY。
- app/services/embedding_factory.py 默认返回 deterministic + memory；qdrant 模式显式构造 QdrantVectorStore。
- docker-compose.yml 的 AI Service 不再依赖 qdrant/ollama 启动；默认环境为 memory。
- qdrant-client 固定在 requirements-qdrant.txt，不放入默认 requirements.txt。
- fastembed 固定在 requirements-fastembed.txt，不放入默认 requirements.txt；默认 deterministic 不下载模型。
- FastEmbed 默认模型配置为 `BAAI/bge-small-en-v1.5`、384 维；显式更换模型时必须同步 `AI_FASTEMBED_DIMENSION`。
- `POST /api/ai/embed` 当前通过 `MemoIndexDocument` 索引完整 Memo，并写入 `source_type=memo`、`index_version=memo-v1` metadata；没有 chunking。
- `AI_INDEX_ON_WEBHOOK=false` 是安全默认；开启后 Webhook 返回 `index_status`，并执行 created/updated upsert、deleted delete。
- `AI_FASTEMBED_CACHE_DIR` 是可选缓存目录；Compose 显式映射 `/app/model-cache` 到 `ai-model-cache` named volume。
- `GET /api/ai/index/health` 是只读状态接口；memory 返回本地 ready，Qdrant 返回 collection status，查询失败返回 unavailable。
- Compose Qdrant 镜像固定为已验证的 `latest@sha256:75eab8c4...`，服务端版本为 1.18.2。

## 真实环境验证

本机已安装 `qdrant-client==1.18.0`，Docker Desktop Linux Engine 已启动，Qdrant 服务端为 1.18.2。使用 `python -m scripts.smoke_qdrant` 已完成真实 FastEmbed 384 维 collection/upsert/search/delete smoke，临时 collection 已清理。FastEmbed+Webhook create/update/delete smoke 也已通过。默认 Compose 仍为 deterministic + memory。

Phase 3f 持久化验证：`devmemoai_qdrant-data` 挂载到 `/qdrant/storage`；临时 collection `devmemo_phase3f_persistence_20260713` 在 `docker compose restart qdrant` 后恢复，`persist-1`、`memo-persist-1` 和 `phase3f` metadata 均保留。验证后已清理 collection，未删除 volume。

缓存验证：`AI_FASTEMBED_CACHE_DIR=H:\DevMemoAI\ai-service\model-cache` 的 64.07 MB 缓存可在 `HF_HUB_OFFLINE=1` 下加载。直接从网络迁移时曾收到 Hugging Face `RemoteProtocolError`，因此使用已有成功缓存完成本地离线验证。

Phase 3g 验证：默认 memory 的 `/api/ai/index/health` 返回 ready；真实 Qdrant 临时 collection 返回 green；Qdrant fake offline health 返回 unavailable；FastEmbed 初始化失败包含 cache_dir 和修复提示。AI Service 66 tests 通过。

可重复命令：

~~~powershell
Set-Location H:\DevMemoAI\ai-service
.\.venv\Scripts\python.exe -m scripts.smoke_qdrant
~~~

该脚本默认一次性加载 FastEmbed；低 CPU 日常路径仍使用 Compose 的 deterministic + memory。可用 `--provider deterministic` 做无模型下载的 Qdrant adapter smoke。

前端全量测试、TypeScript 和 build 通过；`pnpm lint` 报告 377 个仓库既有 Biome CRLF 诊断，本轮未格式化无关文件。

## 下一阶段

使用 docs/prompts/NEXT_STAGE_PROMPT.md，执行 Phase 5e chunk 检索与可观测性收敛。
