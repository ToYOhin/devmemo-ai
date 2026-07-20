# DevMemo AI 变更记录

## 2026-07-20：Phase 10 route B Context Pack Chrome/Windows 复制复核

- 通过同一 Chrome profile 的新标签恢复详情页验收，避免 Vite 重启后接管长期用户标签的超时；确认 accepted Insight、显式来源和 `max_chars=64` 的可见预算截断。
- 用真实 Chrome 指针点击逐一复核 `Copy Markdown`、`Copy JSON` 后，Windows `Get-Clipboard` 分别确认安全 Markdown 标题和可解析的 `context-pack-v1` JSON；未记录 raw clipboard 内容，且没有 raw payload/secret 标记或 console/React error boundary。
- 早先自动化桥接点击未改写 clipboard 的结果保留为工具路径限制，不再作为产品复制状态的结论。
- 未创建/删除 Memo，未再次改变 Insight 状态，未修改 public chunk、公共 chat、Memos 核心、SQLite schema、collection 或 volume。

## 2026-07-20：Phase 10 route B 本地 Webhook → Insight → Review

- 在用户允许的本地 Compose 拓扑中，Memos 启用 `--allow-private-webhooks`，当前已认证用户创建一个指向 AI Service 的既有 Webhook；浏览器不持有 signing secret，`AI_PUBLIC_CHUNK_RETRIEVAL=false` 未改变。
- 对既有非敏感测试 Bug Report 做普通认证 UI 更新后，真实事件被 Memos 投递并由 AI Service 处理。修复 Memos webhook `memos/<uid>` 与详情页终端 UID 不一致导致的派生状态孤岛；新增回归测试。
- 一个持久化 Insight 按已授权的一次操作变为 `accepted`，版本为 `2`。未创建第二条 Memo，未删除数据，未 seed SQLite、绕过认证或修改公共 chat/collection/volume。
- 纠正此前 host-default lifecycle 误读：运行中 Compose 必须在 AI Service 容器执行只读 aggregate CLI。新增本地 Vite `.env.example`，并让 `DEV_PROXY_SERVER` 可从忽略的 `.env.local` 读取，以便重启后稳定指向本机 Compose。
- 验证：新增回归 `1 passed`；AI Service 全量与串行 `verify-devmemo.ps1` 均 `188 passed`（1 条既有弃用警告）；Compose config、串行 Web `33 files / 149 passed`、build、项目 lint 通过。独立 strict TypeScript 仍是 13 条既有依赖/声明错误。
- 仍未验证：delete/revoke 和四项真实参与者反馈。浏览器预算与 Markdown/JSON 系统复制已有本轮技术复核，但不能把它们改写为人工主观反馈通过。

## 2026-07-20：Phase 10 route B 真实 Capture 阻塞

- 已在认证 Memos UI 保存一条非敏感测试 Bug Report，并在详情页确认 Context Pack 入口；不记录 Memo ID 或原文。
- 保存后只读 lifecycle aggregate 仍为 `memo_insights=0` 和一个既有 `processed` webhook event，故严格停在 Capture。没有 accept/reject、pack 生成/预算截断、复制、删除/撤销或人工反馈 pass。
- 新增 [`docs/handoffs/2026-07-20-devmemory-feedback-capture-blocked.md`](handoffs/2026-07-20-devmemory-feedback-capture-blocked.md)；下一步只能先低 CPU、只读诊断正常集成是否能为该现有测试 Memo 产生 Insight，不能再创建测试 Memo 或 seed SQLite。

## 2026-07-20：Phase 10 route B execution authorization

- 已记录真实参与者对“一条非敏感测试 Bug Report + 一次 Insight accept/reject”的授权；删除/撤销仍必须在操作前单独确认。
- `NEXT_STAGE_PROMPT.md` 与 real-feedback plan 已收紧到该范围，不授权 SQLite seed、Memos 登录绕过、第二次 review 状态变更或 public-chunk rollout。

## 2026-07-20：低 CPU 默认运行与验证

- 默认 Compose 的 Memos/AI Service CPU 上限调整为 `0.75`/`0.25`，Memos 使用 `GOMAXPROCS=1`；AI 数值线程环境变量固定为 `1`。
- Qdrant 与 Ollama 改为显式 `qdrant`/`ollama` Compose profile，普通 deterministic + memory 启动不再拉起可选向量库或模型服务。
- `scripts/verify-devmemo.ps1` 的 Go 环境和可选 FullBackend 测试改为单处理器、`go test -p 1`；功能契约未改变。
- 验证：Compose/profile config、运行中 Docker 配额/线程检查、AI health 均通过；串行 `verify-devmemo.ps1` 为 `187 passed`（保留既有 Starlette/httpx 弃用警告）。

## 2026-07-20：Phase 10 route B real-feedback plan

- 新增 [`docs/handoffs/2026-07-20-devmemory-real-feedback-plan.md`](handoffs/2026-07-20-devmemory-real-feedback-plan.md)，把下一步限定为一位在场且同意的真实参与者完成一次 Bug Report `Capture -> Insight -> Review -> Context Pack`。
- 计划明确登录态/SQLite 对齐、安全摘要、accept/reject、revoke/delete、预算截断、Chrome Markdown/JSON 复制、四项人工反馈问题和停止条件；无参与者、无 Insight、状态不一致或异常时只记录阻塞，不伪造闭环。
- 没有运行时代码/API/配置变化，`AI_PUBLIC_CHUNK_RETRIEVAL=false`、公共 chat、Memos 核心和 collection/volume 不变。

## 2026-07-20：Phase 10 DevMemory feedback observation boundary

- 选择 route B，仅以只读方式观察已登录本地 Memos 中的一个真实 Bug Report capture；新增 [`docs/handoffs/2026-07-20-devmemory-feedback-observation.md`](handoffs/2026-07-20-devmemory-feedback-observation.md) 记录可复核事实与未验证边界。
- Compose/AI health 正常，匿名 Memos `auth/me` 为 `401`；只读 lifecycle report 的 AI SQLite aggregate 为 `memo_insights=0`、一个 processed webhook event。后续只读 Chrome 复核已正确渲染空 `/inbox`；先前旧 Memo body 为不可复现的陈旧观察，仍不把页面历史展示写成 accepted/rejected 的持久化证据。
- 定向回归：MemoInsight、Context Pack builder/golden 与 lifecycle report `15 passed`。没有执行 accept/reject、删除/撤销、预算截断、复制或任何持久化变更；无人工参与者反馈，不能视为完整 DevMemory feedback pass。
- 完整 AI Service 与 `scripts/verify-devmemo.ps1` 均为 `187 passed`（保留既有 Starlette/httpx 弃用警告），Compose config 通过。文档切片后按用户 CPU 节制要求未重跑 Web test/build/lint；strict TypeScript 仍为既有 13 项依赖声明/`src/types/view.d.ts` 错误。
- `AI_PUBLIC_CHUNK_RETRIEVAL=false`、公共 `/api/ai/chat`、Memos 核心、collection/volume 和浏览器 secret 边界均未改变。

## 2026-07-20：Phase 10 本地 gateway contract evidence

- 新增 `ai-service/scripts/public_chunk_gateway_contract_smoke.py`，以进程内受信任网关模拟器对精确 raw-body HMAC 和签名绑定的 `visible_memo_ids` 进行本地 smoke；输出只含状态码证据，临时 secret 不写入输出。
- 覆盖 feature flag disabled `503`、缺签名/篡改 body `401`、重复可见范围 `422`、degraded store `503`，以及授权范围内同 Memo 去重和 metadata 脱敏 `200`。
- 验证：public chunk API/retrieval/script 定向 `8 passed`；脚本输出 `PUBLIC_CHUNK_GATEWAY_CONTRACT_SMOKE_OK`。保留既有 Starlette/httpx 弃用警告。
- 完整门禁：AI Service `187 passed`；Web `33 files / 149 passed`、build、项目 `pnpm lint` 通过。单独 strict `pnpm exec tsc --noEmit` 因既有第三方声明和 `src/types/view.d.ts` 的 13 个错误未通过；本轮未触及前端或依赖，项目定义 lint 的 `--skipLibCheck` 类型检查通过。
- 未验证：真实受信任网关、部署环境权限映射、灰度流量和关闭 flag 回滚演练。因此这不是 rollout pass；`AI_PUBLIC_CHUNK_RETRIEVAL=false`、`/api/ai/chat`、Memos 核心、collection/volume 均未改变。

## 2026-07-20

### Context Pack Chrome system-clipboard acceptance

- 修复 Context Pack 复制后的 React error boundary：复制状态不再动态替换 SVG 图标，避免 Chrome 环境中的 DOM `insertBefore` 失败。
- 复制流程优先使用 DOM copy，再回退至异步 Clipboard API；真实 Chrome 验收确认 Markdown 和 JSON 均写入 Windows 系统剪贴板，且来源可追溯、JSON 可解析。
- 验证：Web `33 files / 149 passed`、TypeScript、lint、`git diff --check` 通过。没有修改 AI Service、Memos 核心、公共 chat 或 public-chunk 默认配置。

## 2026-07-20

### Phase 8：public-chunk-v1 受控实现

- 实现独立 `POST /api/ai/v1/chunks/search`，不修改 `/api/ai/chat`、完整 Memo citation 或 `memo-v1` collection。
- 默认 `AI_PUBLIC_CHUNK_RETRIEVAL=false`；启用时必须配置 `AI_PUBLIC_CHUNK_SECRET`，由受信任网关在 `X-DevMemo-Chunk-Signature` 对完整 JSON body 签名。签名 body 中的 `visible_memo_ids` 是 AI Service 强制执行的可见范围，不把 Memos 权限复制进 AI Service。
- 返回固定 `public-chunk-v1` / `memo-chunk-v1`，按 score、memo_id、chunk_index、chunk_id 稳定排序，同 Memo 只保留最高分；metadata 严格仅含 `source_type` 和可选 bounded `title`。
- 回滚只需关闭 flag；不删除 Qdrant collection/volume，不迁移现有 chat。
- 定向 public chunk/API/chat tests：13 passed；AI Service 全量 186 passed（保留 1 个既有 Starlette/httpx 弃用警告）；verify 脚本与 Compose config 通过。

## 2026-07-20

### Phase 9f：Context Pack golden output 与本地生命周期诊断（最小切片）

- Shared `contracts/context-pack-v1.json` now contains expected Markdown/JSON golden cases. Python and Web assert the same deterministic sort, dedupe, accepted-only filter, budget truncation, and deidentified source output.
- Canonical wire JSON is compact snake_case. The fixture caught and fixed a Web trailing-newline drift, so Markdown is now byte-for-byte identical too.
- Added `python -m scripts.devmemory_lifecycle_report`: a read-only local CLI that reports safe aggregate AI-owned SQLite lifecycle counts only; it creates no database, exposes no IDs/content/payloads/secrets, and adds no HTTP/worker/telemetry service.
- Verification: AI `179 passed` (one existing deprecation warning); Web `33 files / 149 passed`; verify script, Compose config, TypeScript, build, lint, and diff check passed.
- Next: finish Phase 9f manual Context Pack feedback and controlled lifecycle evidence; keep Phase 8 public chunk API pending.

## 2026-07-15 人工验收问题修复

- 修复 Context Pack 对 `memos/{uid}` 与 `{uid}` 混用导致的当前 Memo 重复来源；取消全部来源后仍保留来源选择器，可恢复空态。
- 删除 Memo 的 AI 派生状态清理补齐 `memo_chunk_index_state`；同时修正 chunk 删除顺序，先清理向量/生命周期再清理 SQLite 状态，并增加 webhook 回归测试。
- Context Pack copy 增加标准浏览器 DOM clipboard fallback；当浏览器同时禁用 `navigator.clipboard` 与 `document.execCommand` 时，现自动选中预览并提示用户按 `Ctrl+C`，不再误报 copy failure。真实 Chrome 自动复制仍需复验。
- 人工验收覆盖两条 Memo、AI Inbox Accept/Reject、accepted-only pack、显式跨 Memo 选择、预算截断和截图；Phase 8 public chunk API 及公共 chat 未改动。

## 2026-07-14 人工功能检查修复

- Compose 默认 CORS 同时允许 `localhost:3001` 与 `127.0.0.1:3001`。
- 源码变更后的本地启动示例改为 `docker compose up -d --build`，避免 AI Service 继续运行旧镜像。
- `POST /api/ai/summarize` 现在会为显式 Code Snippet/Bug Report 持久化详情页模板；默认 chat 和完整 Memo 检索不变。

### Phase 9 路线提案：DevMemory Loop

- 新增下一阶段方向：AI Inbox + Decision Ledger，将 Memo 派生为可审核、可撤销、可追溯的 fact/decision/action/bug insight。
- 对比 Memos、Khoj、AnythingLLM、AFFiNE、Logseq、Outline 后，确定不复制第三方源码、不引入通用 agent 平台，优先构建 provenance + approval + temporal lifecycle 差异化。
- `docs/prompts/NEXT_STAGE_PROMPT.md` 已切换到 Phase 9；Phase 8 public chunk API 仍保持 pending approval。

### Phase 9a：AI Inbox / Decision Ledger 首个垂直切片

- 新增 provider-neutral `MemoInsight` contract，包含稳定 ID、来源 Memo、类型、置信度、版本和 pending/accepted/rejected 生命周期。
- 复用现有 parser 为 Code Snippet、Bug Report 和 plain Memo 生成有限 deterministic 候选；AI Service SQLite 按 Memo/类型幂等 upsert，语义变化重置 pending 并递增版本。
- 新增内部 `POST /api/ai/insights/preview`、`GET /api/ai/insights/{memo_id}` 和显式状态变更 API；preview 不落库，过期 approve/reject 返回 409。
- Memo 详情页新增 AI Inbox 卡片，展示类型、置信度、状态、来源和 approve/reject；不暴露原始 content，不改变公共 chat 或 public chunk API。
- 验证：AI Service 162 passed；前端 136 passed；TypeScript/build/lint、Compose API smoke 和人工页面截图通过。
- 下一阶段：Phase 9b 只定义已确认 insight 的 bounded Context Pack contract/fixture。

### Phase 9b：Context Pack contract / fixture

- 新增 `context-pack-v1` provider-neutral contract：显式 `question`、`memo_ids`、`insight_ids`、`max_chars` 和 `max_items`。
- 新增纯函数 `build_context_pack`，拒绝未知 ID、pending/rejected insight 和隐式 Memo 扩展；只使用 Memo title/summary、已确认 insight 和 source_refs。
- 输出提供可复制 Markdown、稳定 JSON、唯一 sources、confidence/updated_at/稳定 ID 排序以及明确截断原因；不新增 HTTP、Qdrant、公共 chat 或 Agent 行为。
- Context Pack contract/fixture 定向 12 passed；AI Service 全量 174 passed，保留既有 Starlette/httpx 弃用警告。
- 下一阶段：Phase 9c 只评估 Context Pack 的内部入口、权限和撤销边界。

### Phase 9c：Context Pack integration gate（proposal-only）

- 完成产品入口评审，推荐 Memo 详情页 AI Inbox 内的“复制 Context Pack”，默认当前 Memo，跨 Memo 必须显式选择；命令面板/独立页面暂不采用。
- 明确权限与撤销：只允许当前用户可见 Memo 和 accepted insight；pending/rejected、删除 Memo、撤销 insight、过期版本和不可见来源排除，pack 不持久化。
- 明确交互边界：Markdown 主复制格式、JSON 可选；question、选择、预算、sources、截断、空态、失败态和窄屏必须可见；不暴露 raw content、Webhook payload、secret 或 chunk content。
- 当前没有产品批准，本阶段不修改运行时 UI/API；下一阶段为 Phase 9d internal preview/copy approval gate。

### Phase 9d：Memo 详情页 Context Pack internal preview/copy

- 用户明确批准后，在现有 Memo 详情页 AI Inbox 增加 Context Pack 面板；默认当前 Memo 与 accepted insights，来源可逐项取消，当前不自动发现跨 Memo 来源。
- 新增 question、`max_chars`/`max_items`、bounded Markdown preview、Markdown/JSON copy、sources 和截断提示；empty、AI 查询失败、clipboard 失败和窄屏状态均有覆盖。
- Web 端只镜像 Phase 9b `context-pack-v1` builder contract，在内存生成，不新增公共 HTTP、不写 SQLite、不连接 Qdrant、不启动 Agent/worker；raw content、Webhook payload、secret 和 chunk content 不进入 pack。
- 验证：Web 定向 7 passed；全量 33 files / 143 passed；TypeScript/build/lint 通过；Playwright 手动验证登录、approve、复制、截断和 390px 窄屏，截图 artifact 为 `devmemo-phase9d-context-pack-desktop.png`、`devmemo-phase9d-context-pack-mobile.png`。
- 下一阶段：Phase 9e 评审共享 contract fixture、权限感知跨 Memo 显式选择和 Memo 删除/insight 撤销联动；Phase 8 public chunk API 继续 pending approval。

### Phase 9e：共享 fixture、权限感知跨 Memo 选择、删除/撤销联动

- 新增共享 `contracts/context-pack-v1.json`，Python Context Pack fixture 与 Web contract test 使用同一输入，减少排序、预算、accepted 状态和脱敏语义漂移。
- Memo 详情页 Context Pack 从 Memos 当前用户可见列表提供跨 Memo 选项；默认只选当前 Memo，其他 Memo 必须显式勾选，跨 Memo insight 查询失败会提示并排除，不会读取 raw content。
- Memos deleted Webhook 增加 AI 派生状态清理，删除 `ai_notes`、`memo_templates`、`memo_insights`；不触碰 Memos 数据库、原始 Markdown、公共 chat 或 Qdrant volume。
- reject 继续作为 insight 撤销语义，状态版本递增、React Query 失效和 Context Pack accepted-only 过滤共同保证撤销来源不再进入 pack；过期版本仍返回 409。
- 验证：Context Pack 定向 12 passed；Webhook 定向 8 passed；AI Service 全量 175 passed；Web 全量 33 files / 147 passed；TypeScript、build、lint 与 `git diff --check` 通过。
- 下一阶段：Phase 9f 评估 Context Pack/Insight 生命周期观测、用户反馈和跨语言 golden output；Phase 8 public chunk API 继续 pending approval。

## 2026-07-14

### Phase 5f：Qdrant chunk collection/config/composition
- 增加 `QDRANT_CHUNK_COLLECTION`，默认 `devmemo_memo_chunks`，并通过 Compose 透传；配置层拒绝空名称或复用完整 Memo collection。
- fake Qdrant contract 明确校验独立 collection 的 provider dimension 和 Cosine distance；chunk `memo-chunk-v1` 与完整 Memo `memo-v1` 继续隔离。
- 组合根已接入 chunk store 选择：仅在 `AI_INDEX_MODE=chunk` + `AI_VECTOR_STORE=qdrant` 时使用独立 Qdrant collection，其他 chunk 路径继续使用独立 memory。
- chunk health 复用所选 VectorStore 的 provider/status/point_count，默认 deterministic + memory、Webhook `code=0` 和公共 chat 契约不变。
- 新增内部 `ChunkRetrievalService`、`ChunkCitation`、`ChunkRetrievalResult`，严格验证 `memo_id`、`chunk_id`、`chunk_index`、`index_version` 和 chunk source metadata；原文只保留在服务端 context。
- 扩展 `scripts/smoke_qdrant.py --mode chunk`，验证 health、upsert/search、重新连接后的点数和检索持久性、内部 chunk contract、delete；临时 collection 自动清理。
- 聚焦验证：AI Service 24 passed；保留既有 Starlette/httpx 弃用警告。Docker Desktop/Qdrant 恢复后真实 chunk smoke 返回 `QDRANT_CHUNK_SMOKE_OK`，health、重连持久性、内部 contract 和 delete 均通过。
- Phase 5g rollout gate：AI Service 153 passed；前端 131 passed；TypeScript/build/lint、Compose config 和 Go `go test -p 2 ./...` 通过；Qdrant Server 1.18.2。
- rollout 结论：chunk retrieval 继续保持内部边界，不接入公共 `/api/ai/chat`，不修改完整 Memo collection。
- Phase 6 compatibility decision：现有 `embedding_id`/`retrieved_count` 继续表示完整 Memo；不启用隐式 chunk mode，不新增未定义公共 chunk endpoint；未来公开接入必须先定义版本化 contract、去重/排序、脱敏和迁移回滚。
- Phase 7 public chunk API proposal：定义未来 `POST /api/ai/v1/chunks/search` / `public-chunk-v1`、默认关闭、固定 memo-chunk-v1、同 Memo 最高分去重、确定性排序、脱敏和灰度回滚；本阶段未实现路由。
- Phase 8 implementation gate：当前没有明确产品/兼容批准，保持 proposal pending approval，不实现公共路由、不启动灰度。
- 下一阶段：收到明确批准后再执行 Phase 8 implementation slice。

### 单 Agent 接管模式
- 后续开发统一使用 `H:\DevMemoAI` 主工作树和单一 Agent，停止 Terra/Luna 并行推进，保留 `project4` worktree 作为历史/回滚参考。
- 新增 `docs/handoffs/2026-07-14-single-agent-handoff.md`，固化当前结构、验证基线、未完成项和新窗口接管步骤。

### Phase 5e：chunk 检索与可观测性收敛
- 新增 provider-neutral `ChunkIndexStateStats`/`ChunkIndexHealth`，对照 VectorStore 点数与 SQLite 登记状态。
- 新增只读 GET `/api/ai/index/chunk-health`，显式返回 chunk mode/version、provider、点数、登记 Memo/chunk 数和状态后端；状态异常返回 degraded。
- 覆盖空状态、生命周期计数、版本隔离、SQLite 状态读取和 HTTP contract；不改变完整 Memo chat、默认 deterministic + memory 或公共索引 health。
- 验证：AI Service 144 passed；后续执行前端、Go、Docker 和完整验证门禁。
- 下一阶段：Phase 5f Qdrant chunk 持久化与显式 chunk 检索。

### 文档与项目结构同步
- 根据当前仓库实际目录更新 `docs/structure.md`，补充 Memos Go/React、AI Service domain/services/adapters、AI SQLite、Webhook 和 Compose 边界。
- 同步 `README_AI.md`、`docs/architecture.md`、`docs/development.md`、`docs/api.md`、`docs/oss-adoption.md` 和项目状态中的 Phase 5d/5e、lint 与结构事实。
- 明确默认完整 Memo 索引与显式 chunk Webhook 索引使用独立存储，避免误解为 chunk 已替换公共 RAG 路径。

### Phase 5d：可选 chunk 索引生命周期
- 新增 provider-neutral `ChunkLifecycleCoordinator`，显式 `AI_INDEX_ON_WEBHOOK=true` + `AI_INDEX_MODE=chunk` 后支持 chunk create/update/delete。
- 更新先 upsert 当前 `memo-chunk-v1` chunk，再删除同一 Memo 的 stale 尾部；空内容和删除事件会清理已登记 chunk。
- AI Service SQLite 新增 `memo_chunk_index_state`，只保存索引版本和 chunk ID 列表，支持重启后的安全清理，不保存原始 Markdown。
- chunk lifecycle 使用独立 InMemoryVectorStore，不污染完整 Memo chat 检索源；Qdrant chunk collection 留到后续阶段。
- 默认 `AI_INDEX_MODE=memo`、完整 Memo `memo-v1`、Webhook `code=0`、公共 chat citation 和 Compose deterministic + memory 均保持不变。
- 验证：AI Service 142 passed；Go 全量、前端 131 tests、TypeScript/build、pnpm lint 和 Compose config 通过。
- 下一阶段：Phase 5e chunk 检索与可观测性收敛。

### Phase 5c：chunk 离线检索评估
- 新增 provider-neutral `OfflineChunkIndex`，使用 deterministic + memory 构造独立 chunk 试验索引，不改变完整 Memo 生产索引。
- 复用 `RetrievalService` 和 Phase 5a `RetrievalEvaluator`，对照 Recall@K/首个相关结果排名；chunk citation 保留 Memo、chunk 和版本 metadata，上下文保留原始 chunk 内容。
- 覆盖 upsert、更新后的显式 stale delete、重复/空 chunk 和完整 Memo baseline 对照 contract tests；不访问网络、不加载模型、不连接 Qdrant。
- 验证：AI Service 133 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。
- 下一阶段：Phase 5d 可选 chunk 索引生命周期。

### Phase 5b：Memo chunking 边界
- 新增 provider-neutral `MemoChunk` 和纯函数 `chunk_memo`，按换行边界/字符上限切分，同时保留 Markdown 原始字符序列。
- 使用 `memo-chunk-v1` 与 `index_mode=chunk` metadata；chunk ID 由 Memo、版本和位置稳定派生，支持更新复用和显式 stale ID 删除。
- 增加空内容、超长内容、更新/删除、重复 ID 和 metadata 复制 contract tests；不接入默认 Webhook、Qdrant、FastEmbed 或生产索引。
- 验证：AI Service 129 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。
- 下一阶段：Phase 5c chunk 离线检索评估。

### Phase 5a：离线检索质量评估边界
- 选择离线评估而不是直接切换 chunking，避免破坏当前完整 Memo 的索引、删除和 citation 契约。
- 新增 provider-neutral `RetrievalEvaluationCase`、`RetrievalEvaluationResult` 和 `RetrievalEvaluator`。
- 支持 Recall@K、相关 Memo 命中列表、首个相关结果排名和批量案例；不访问网络、不加载模型、不连接 Qdrant。
- 验证：AI Service 116 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。
- 下一阶段：Phase 5b Memo chunking 边界，仍需保持完整 Memo 索引兼容。

### Phase 4g：显式清理批准与审计边界
- retention preview 现在返回 `cutoff`、`preview_limit` 和 `candidate_ids`，清理请求必须绑定同一预览集合。
- 新增 `POST /api/ai/ops/outbox/retention-cleanup`：默认 dry-run，只有显式 `confirm=true` 且 `dry_run=false` 才能删除终态 outbox 记录。
- SQLite 事务再次校验 preview 集合、cutoff 和 `processed/failed` 状态；pending、越界 ID 或数据变化整批拒绝。
- 新增 `webhook_cleanup_audits` 和 cleanup-audits GET；记录 approval、actor 摘要、cutoff、候选数、删除数和时间，相同 approval_id 幂等。
- 不删除 Memos、ai_notes、memo_templates、原始 Markdown、Qdrant/AI volume；不引入 worker、队列、定时任务或 Prometheus。
- 验证：AI Service 108 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。
- 下一阶段：Phase 5 检索质量增强（chunk、混合检索、rerank 和评估）。

### Phase 4f：Outbox 保留与告警导出边界

- 新增受 `AI_OPS_TOKEN` 保护的 `GET /api/ai/ops/outbox/retention-preview`，只读预览 30 天以上未更新的 processed/failed 事件，不自动删除、不影响 pending。
- 新增受保护的 `GET /api/ai/ops/alerts`，导出失败数、耗尽重试数和最多 5 条 warning/critical 错误摘要。
- 告警接口不推送外部服务，不返回 payload、secret 或未截断错误；没有引入 worker、Redis、Prometheus 或新依赖。
- 验证：AI Service 105 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。
- Phase 4f 的显式清理批准、审计记录和 retention 删除执行已在 Phase 4g 完成。

### Phase 4e：运维 API 安全与告警边界

- 新增可选 `AI_OPS_TOKEN` 与 `X-DevMemo-Ops-Token`，配置后保护 outbox GET 和显式 retry POST；未配置时保持本地兼容。
- 公开 outbox 响应移除原始 Webhook payload，错误摘要归一化为单行并限制在 240 字符以内；SQLite 内部数据不变，retry 仍可用。
- 新增认证、默认兼容、错误摘要截断和 retry 端点保护测试。
- 未引入认证服务、Redis、Prometheus、后台 worker 或前端运维 UI；主动告警推送留到 Phase 4g。

### Phase 4d：显式有限重试与最小观测

- AI Service 自有 `webhook_events` 兼容补充 `max_attempts`，默认每个事件最多 3 次总处理尝试。
- 新增 `POST /api/ai/ops/outbox/{event_id}/retry`，只允许失败事件显式重试；达到上限返回 409，成功清除旧错误。
- GET outbox 增加 `by_status` 和最多 5 条 `recent_errors`，不启动后台 worker 或新增运行时依赖。
- 默认 deterministic + memory、Memos Webhook `code=0` 和 HMAC 显式开关保持不变。
- 验证：AI Service 100 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。
- Phase 4d 不包含 ops API 认证、错误摘要脱敏和告警轮询；前两项已在 Phase 4e 完成，告警轮询已在 Phase 4f 完成。

### Phase 4c：Webhook Outbox 与失败状态读取

- AI Service SQLite 新增兼容 `webhook_events` 表，保存事件 payload、状态、尝试次数和最后错误。
- Webhook 按显式 `eventId` 或 body hash 幂等入队，重复事件不重复处理；处理失败仍返回 `code=0` 并记录 `failed`。
- 新增 GET `/api/ai/ops/outbox`，支持按状态和数量读取最近事件；不启动后台 worker。
- 验证：AI Service 95 passed；Go 全量、前端 131 tests、TypeScript/build、Compose config 通过。
- 未完成：自动重试执行、限流和指标观测留到 Phase 4d。

### Phase 4b：Webhook HMAC 安全边界

- 新增可选 `AI_WEBHOOK_SECRET` 和 `X-DevMemo-Signature: sha256=<hex>` HMAC-SHA256 校验。
- 默认未配置 secret 时保持现有 Webhook 兼容行为；显式配置后无效签名返回 401。
- 使用原始 request body 和标准库 `hmac.compare_digest`，不增加第三方依赖或默认外部服务。
- 验证：AI Service 90 passed；Go `go test -p 2 ./...`、Compose config、前端 131 tests、TypeScript/build 均通过。
- `pnpm lint` 仍受仓库既有 377 个 Biome CRLF 诊断阻塞，本轮未格式化无关前端文件。

### Phase 4：RAG 检索与引用问答最小切片

- 新增 provider-neutral `RetrievalService`，按问题 embedding、向量搜索和完整 Memo 上下文组装执行检索。
- 新增 `POST /api/ai/chat`，返回答案、`memo_id`/`embedding_id`/`score`/metadata 引用、provider 和检索数量。
- 默认 deterministic + memory 支持无网络问答；空知识库、非法 limit、检索故障和 LLM 故障有明确契约。
- 原文仅作为索引派生上下文使用，公共 citations 不返回内部 `content` 字段；未引入 chunk/rerank 或前端聊天 UI。
- 验证：AI Service 79 passed；Go `go test -p 2 ./...`、Qdrant deterministic smoke、Compose config、前端 131 tests、TypeScript/build 均通过。
- `pnpm lint` 仍受仓库既有 377 个 Biome CRLF 诊断阻塞，本轮未格式化无关前端文件。

### Phase 3g：索引运行健康与故障边界

- 新增只读 `GET /api/ai/index/health`：memory 返回 ready，Qdrant 返回 collection status/point_count。
- Qdrant health 查询异常降级为 `available=false、status=unavailable`，不让默认 memory 路径连接 Qdrant。
- FastEmbed 初始化错误现在包含 cache_dir 和缓存修复提示。
- Qdrant 镜像固定到已验证的 Server 1.18.2 digest：`sha256:75eab8c4...`。
- 验证：AI Service 66 passed；真实 Qdrant health smoke 通过；Go 全量、前端 131 tests、TypeScript/build 通过。
- 未完成：RAG 检索、Memo chunk 和 `/api/ai/chat`，留到 Phase 4。

### Phase 3f：Qdrant 持久化与 FastEmbed 缓存治理

- Compose 为 AI Service 增加 `ai-model-cache:/app/model-cache`，并新增 `AI_FASTEMBED_CACHE_DIR`；默认 deterministic + memory 不加载模型。
- 验证 `devmemoai_qdrant-data` 挂载到 `/qdrant/storage`；`docker compose restart qdrant` 后 collection、point 和 payload 恢复成功。
- FastEmbed 384 维模型在 `H:\DevMemoAI\ai-service\model-cache` 离线加载成功，缓存约 64.07 MB。
- 首次直接迁移下载因 Hugging Face 代理 `RemoteProtocolError` 失败，随后复用已验证缓存完成离线 smoke；该环境限制已记录。
- AI Service：62 passed；Qdrant volume restart smoke：通过；Compose config：通过。
- 未完成：Qdrant health/故障降级边界和镜像版本固定评估，留到 Phase 3g。

### Phase 3e：Qdrant 真实 collection smoke

- Docker Desktop Linux Engine 已启动，Compose Qdrant 服务端返回 1.18.2。
- 安装可选 `qdrant-client==1.18.0`，不加入默认 requirements，Compose 默认仍为 deterministic + memory。
- 新增 `ai-service/scripts/smoke_qdrant.py`，验证真实 collection 创建、FastEmbed 384 维 upsert、search、payload 和 delete；临时 collection 已清理。
- FastEmbed+Qdrant 真实 smoke：通过；删除后目标向量不再出现在搜索结果中。
- AI Service 全量测试：60 passed；安装 qdrant-client 后的缺依赖契约测试通过模块注入模拟。
- 未完成：Qdrant volume 重启持久化和 FastEmbed 模型缓存持久化目录评估，留到 Phase 3f。

### Phase 3c：可选 FastEmbed Provider 与 Memo 索引边界

- 新增可选 `FastEmbedEmbeddingProvider`，第三方 SDK 只存在于 adapter。
- 新增 `AI_EMBEDDING_PROVIDER`、`AI_FASTEMBED_MODEL` 和 `AI_FASTEMBED_DIMENSION`；默认 deterministic、不下载模型。
- 新增 `requirements-fastembed.txt`，固定 fastembed 0.8.0。
- 新增 `MemoIndexDocument/index_memo`；当前一个完整 Memo 对应一个向量，补充 `source_type` 和 `index_version` metadata，不做 chunk/RAG。
- 验证：AI Service 54 passed；前端 131 passed；TypeScript/build、Compose config、根验证通过。
- FastEmbed 真实 smoke 已通过：首次加载约 23.48 秒，单条推理约 0.06 秒，384 维；模型缓存约 64.07 MB。
- 未验证：真实 Qdrant 网络路径，原因是 qdrant-client 未安装且 Docker Linux engine 未运行。
- Commits：c699400、57732f9、0c0d2cb。

### Phase 3d：Webhook 可选索引生命周期

- 新增 `AI_INDEX_ON_WEBHOOK=false`，默认不改变日常 CPU 和 Webhook 索引行为。
- 开启后支持 Memo create/update 稳定 upsert、delete 删除和 `index_status` 状态。
- 索引失败不会阻断摘要、模板持久化和 Webhook `code=0` 响应。
- 验证：AI Service 60 passed；Go 全量测试通过；前端 131 passed；FastEmbed+Webhook 真实 smoke 通过。
- 未验证：真实 Qdrant，因 qdrant-client 未安装且 Docker Linux engine 未运行。
- Commit：4a58e56。

### Phase 3b：可选 Qdrant VectorStore Adapter

- 新增 QdrantVectorStore，实现 VectorStore Protocol 的 upsert、query_points search、delete。
- 使用稳定 UUID 映射 Qdrant point，payload 保存 embedding_id、memo_id、metadata。
- 新增 requirements-qdrant.txt，固定 qdrant-client 1.18.0；默认 requirements 不增加网络依赖。
- 新增 AI_VECTOR_STORE=memory|qdrant，默认 memory。
- AI 容器不再依赖 Qdrant/Ollama 启动。
- fake adapter contract 通过；真实 Qdrant 因本机依赖和 Docker 引擎不可用暂未验证。
- Commits：ee0937c、99ad024。

### Phase 3a：Embedding Provider 与 Vector Store 边界

- 新增 provider-neutral contracts、8 维 deterministic provider、InMemoryVectorStore、EmbeddingService 和 POST /api/ai/embed。
- 验证：AI Service 34 passed；Phase 3a 定向 13 passed。

### Phase 2d：AI 摘要读取与生成 UI

- 新增 GET /api/ai/notes/{memo_id}、摘要展示和生成/重新生成。
- 验证：AI Service 21 passed；前端 131 passed；TypeScript/build 通过。

## 2026-07-12

### Phase 2c：模板展示与复制

- React 展示 Code/Bug 模板、highlight.js 高亮和 Clipboard API 反馈。

### Phase 2b：模板持久化

- memo_templates 按 memo_id 幂等 upsert，保留 raw_content。
