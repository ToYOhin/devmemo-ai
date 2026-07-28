# DevMemo AI 项目状态

## 真实 GitHub CI、GHCR 与 RC 发布资产验证（2026-07-28）

- 已推送 `codex/devmemo-ai-mvp`，PR #1 的 Backend、Frontend 与 AI Service Actions 均为绿色；Store 的 SQLite/MySQL/PostgreSQL 驱动矩阵和 golangci-lint 均在真实 GitHub runner 通过。
- GHCR 发现并修复了一个真实配置缺陷：OCI repository 必须为小写。canary 与 release workflow 现固定使用 `ghcr.io/toyohin/devmemo-ai`；第二次手动 canary 的 `linux/amd64`、`linux/arm64` 构建、合并 manifest 与 runner-side `imagetools inspect` 均通过。
- 经明确授权创建了私有仓库的预发布 `v0.1.0-rc.1`，不是稳定版。Release workflow 成功生成 Linux amd64/arm64/armv7、macOS amd64/arm64、Windows amd64 共六个二进制资产和 `checksums.txt`，并成功发布对应的多架构 GHCR 镜像。
- 本机以低负载下载 Windows ZIP：其 SHA-256 与 Release `checksums.txt` 匹配，解压后的 `devmemo-ai.exe --help` 退出成功；Release 的六个二进制资产名称与校验清单一一对应。证据与后续边界见 [`docs/handoffs/2026-07-28-rc-release-validation-handoff.md`](handoffs/2026-07-28-rc-release-validation-handoff.md)。
- 正式公开发布仍为 NO-GO：仓库仍为 private、`RELEASE_PLEASE_TOKEN` 尚未配置、外部私密漏洞报告渠道尚未确认。当前本机 GitHub OAuth token 也没有 private Packages 的读取授权，故本机直接 GHCR inspect 返回 `403`；这不影响已在 GitHub runner 完成的镜像 inspect，但后续维护者如需本机拉取私有镜像应使用可轮换的最小 `read:packages` token。不得擅自改可见性、设置长期 token 或推稳定 tag。

## 发布前 CI 收敛与外部前置清单（2026-07-28）

- 已修复远端 PR #1 的两个已证实 CI 根因：`store/test` 不再使用会漂移到未来 schema 的 `neosmemo/memos:stable`，而是使用可拉取的 `0.26.2` 迁移 fixture；golangci-lint 从 `3m` 调整为 `5m`，避免已经报告 `0 issues` 时仍因硬超时失败。
- 真实、低负载迁移验证通过：SQLite fixture schema `0.26.5` 串行迁移到当前 `0.28.1`，并验证可写入数据。工作流 YAML 解析与 `git diff --check` 通过。为限制本机 CPU，没有重跑 MySQL/PostgreSQL 全驱动 store 门禁；远端 CI 必须在后续 push 后重新验证。
- GitHub 只读复核：仓库仍为私有，Actions secrets 数为 `0`，因此 `RELEASE_PLEASE_TOKEN` 尚未配置；默认 workflow token 权限为 read，但 release/package 作业已有自己的最小写权限。私有仓库的 private vulnerability reporting API 当前无法确认启用，不能宣称已具备公开报告渠道。
- 公开稳定发布仍为 NO-GO，直到维护者配置 release token，并决定和完成公开可见性/外部私密漏洞报告渠道。真实 CI、RC GitHub Release 与 GHCR 资产已经在本次状态顶部复核；操作清单见 [`docs/release-preflight.md`](release-preflight.md)，最新接管记录见 [`docs/handoffs/2026-07-28-rc-release-validation-handoff.md`](handoffs/2026-07-28-rc-release-validation-handoff.md)。

## 开源发布基础设施：身份、社区、默认部署与 CI 命名空间（2026-07-28）

- 本仓库现明确为非官方的 DevMemo AI 下游项目：新增 `NOTICE`、`UPSTREAM.md`、`GOVERNANCE.md`、`SUPPORT.md`、`CODE_OF_CONDUCT.md` 与贡献说明；README 覆盖项目用途、起步方式、获取帮助、维护者、上游关系和许可证边界。`MIT` 许可证继续适用于本项目与上游兼容范围，未暗示与 Memos 官方关联。
- 默认 `docker-compose.yml` 不再启用 Memos 的 `--allow-private-webhooks`。只有受控本地 Docker 开发拓扑可显式叠加 `docker-compose.local-webhook.yml`；这不改变 AI 默认 deterministic + memory、索引 flag、API、数据库或 Context Pack 边界。
- 发布资产、安装脚本与 Docker 元数据改为 DevMemo 自有 `devmemo-ai` 名称和 `ghcr.io/${github.repository_owner}/devmemo-ai` 命名空间；新增 AI Service 测试工作流。Go module import path 保持上游路径，避免无关的运行时代码改动。
- 验证：默认与本地 override Compose 均通过 `config --quiet`，且仅 override 包含私网 Webhook 放行；安装脚本经容器内 POSIX `sh -n` 与 `--help` 检查，工作流缩进/命名空间检查与 `git diff --check` 通过。没有因本次文档、Compose 或 CI 配置改动重跑应用全量测试。
- 正式公开发布仍未获准：需要先修复既有后端 CI migration 超时、配置发布 token/包权限、启用私有漏洞报告通道，并在真实目标仓库复核 CI、镜像与发布资产。详见 [`docs/handoffs/2026-07-28-open-source-release-foundation-handoff.md`](handoffs/2026-07-28-open-source-release-foundation-handoff.md)。

## Phase 13：strict TypeScript lint gate promotion（2026-07-27）

- `web/package.json` 的 `pnpm lint` 已从 `tsc --noEmit --skipLibCheck && biome check src` 提升为 `tsc --noEmit && biome check src`；Phase 12 已验证的 strict baseline 现在成为日常 Web 门禁。
- 未修改 TypeScript 配置、compat declarations、依赖、lockfile 或运行时代码；所有现有 Context Pack、Memos、AI Service、公共 chat 与 public-chunk 边界不变。
- 验证：新的 `pnpm lint`、独立 strict tsc、Web 全量低并发 `33 files / 149 passed`、production build、`docker compose config --quiet` 与 `git diff --check` 均通过。build 保留既有大 chunk/plugin timing 警告；无后端改动，未重跑 AI Service 全量门禁。
- 当前已定义的内部工程路线至此完成。权威交接为 [`docs/handoffs/2026-07-27-strict-lint-gate-handoff.md`](handoffs/2026-07-27-strict-lint-gate-handoff.md)；后续只在用户选择新产品切片、真实登录态复核或具备 gateway 前置条件时推进。

## Phase 12：Web strict TypeScript baseline（2026-07-27）

- 独立 `pnpm exec tsc --noEmit --pretty false` 已从 15 个既有声明错误收敛到 0；未启用全局 `skipLibCheck`、未关闭 strict、未使用 `any`/`@ts-ignore`，也未新增或升级依赖。
- `src/types/view.d.ts` 不再依赖因同名 `common.ts` 而未进入编译的全局 `FunctionType`，改用明确的 `() => void`，并移除无效的 `common.d.ts`。第三方问题由窄范围类型兼容层处理：TanStack Query Devtools 与 goober 使用仅供 TypeScript 解析的精确 paths，Mermaid/type-fest、React Leaflet deep context 与 Leaflet MarkerCluster 补齐实际需要的声明。
- 兼容层只影响编译期类型解析；production build 继续从已安装 package 解析运行时代码。没有修改 Context Pack、Memos server/store/proto、AI Service、API、数据库、公共 chat、collection/volume 或默认 flags。
- 验证：strict TypeScript 通过；Mermaid/地图定向 `2 files / 2 passed`；Web 全量低并发 `33 files / 149 passed`；build、项目 lint、`docker compose config --quiet` 与 `git diff --check` 通过。未改后端运行时代码，因此未重跑 AI Service 全量门禁。
- 权威交接为 [`docs/handoffs/2026-07-27-web-strict-typescript-handoff.md`](handoffs/2026-07-27-web-strict-typescript-handoff.md)。其后续 Phase 13 已把项目 lint 的 TypeScript 子门禁提升到已验证的 strict baseline；未借机升级依赖或改变运行时行为。

## 项目结构复核与新窗口入口（2026-07-27）

- 当前运行时边界已从实时源码复核：Memos Go 是原始 Memo/权限事实源；AI Service 按 domain/services/adapters 管理派生状态与可选 provider；`MemoView` 内嵌 `AiMemoSummary`、`AiMemoTemplate`、`AiMemoInsights`、`AiMemoContextPack`。
- 默认 Compose 仍只有 Memos + AI Service；Qdrant/Ollama 为显式 profile。默认索引、向量存储和 public chunk flags 未改变。
- 现有 graphify 图停留在 2026-07-12，不包含近期 AI feature，不能单独作为当前结构事实源。
- Phase 12 接管前的 15 个 strict TypeScript 错误已重新运行并分类；现已由 Phase 12 收敛到 0，完成态见 [`docs/handoffs/2026-07-27-web-strict-typescript-handoff.md`](handoffs/2026-07-27-web-strict-typescript-handoff.md)，新窗口 Prompt 为 [`docs/prompts/NEW_WINDOW_PROMPT.md`](prompts/NEW_WINDOW_PROMPT.md)。

## Phase 11：Context Pack copy readiness（2026-07-27）

- 已完成 Web-only Context Pack 复制就绪切片：预览上方现在显示条目数、来源数和 `当前字符数/max_chars`，Markdown/JSON 两个按钮都有一致的已复制状态，并通过 `role=status` + `aria-live=polite` 向辅助技术报告具体复制格式。
- 当 question、来源选择或预算改变并生成新的 pack 时，旧的 copied/manual/error 状态会自动清除，避免把上一次复制结果误认为当前输出已复制。pack 仍只在浏览器内存生成；没有新增 API、SQLite 写入、Qdrant、worker、依赖或公共 chat 行为。
- Web 定向测试 `7 passed`；全量低并发测试 `33 files / 149 passed`；build 与项目 `pnpm lint` 通过。该切片结束时独立 strict `pnpm exec tsc --noEmit` 报告 `15` 个既有第三方声明与 `src/types/view.d.ts` 错误；这些错误已由后续 Phase 12 收敛到 0。
- 真实 Chrome 插件已成功启动并连接。恢复低 CPU 默认 Compose 后，Vite/Memos 通路正常，但当前 Chrome profile 已无有效 Memos 登录态，登录表单也没有浏览器保存凭据；因此没有进入 Memo 详情页，Phase 11 的真实 UI/系统剪贴板复核记为“认证会话缺失，未验证”。没有从 SQLite/token 存储提取身份、伪造会话或修改 Memo/Insight。
- 当前权威交接为 [`docs/handoffs/2026-07-27-context-pack-copy-readiness-handoff.md`](handoffs/2026-07-27-context-pack-copy-readiness-handoff.md)。Phase 10 route B 保持已完成；route A 仍未验证，`AI_PUBLIC_CHUNK_RETRIEVAL=false` 保持不变。

## 当前验证与下一入口（2026-07-20）

- CPU-conservation baseline is applied and verified: default Compose caps Memos `0.75` CPU and AI Service `0.25` CPU, with Memos/Go constrained to one processor. Qdrant and Ollama require explicit profiles; AI numerical thread variables are pinned to one. Runtime inspection, health, Compose config, and serial `verify-devmemo.ps1` (`187 passed`) are recorded in [`docs/handoffs/2026-07-20-low-cpu-baseline.md`](handoffs/2026-07-20-low-cpu-baseline.md).
- Phase 10 route B now has real local integration evidence: the authenticated current user configured one private Docker-network Memos webhook, then made an ordinary UI update to the existing non-sensitive test Bug Report. Memos delivered the event; AI Service persisted one Insight and the authorized review changed it to `accepted` at version `2`. No Memo ID, original content, payload, or secret is recorded.
- The apparent `memo_insights=0` blocker was a diagnostic-path error, not a missing Insight: the host-default report did not see the Compose volume. The live, safe aggregate command is `docker compose exec -T ai-service python -m scripts.devmemory_lifecycle_report`; it reported derived AI state and eight processed webhook events after this run.
- The webhook uses Memos' existing user-level configuration and `--allow-private-webhooks` only so the Compose service name may resolve to the private Docker network. This is a local-development relaxation, not a browser signing path or a public-chunk rollout; `AI_PUBLIC_CHUNK_RETRIEVAL=false` remains unchanged.
- The low-CPU route-B loop reached Capture → Insight → accepted Review → bounded Context Pack → real Chrome/Windows Markdown/JSON system-copy → participant feedback. The participant judged source clarity clear, accepted review trustworthy, the `64`-character budget useful, and copy behavior aligned with expectation. Delete/revoke was intentionally not performed.
- The browser-control issue is now narrowed and recoverable: claiming a long-lived user tab can time out after a Vite restart, while a fresh tab in the same Chrome profile loads the authenticated Memo correctly. That fresh page confirmed the accepted Insight and a `64`-character Context Pack budget with visible `max_chars` truncation and no console errors.
- The earlier browser-automation clipboard mismatch is now isolated to that bridge: real Chrome pointer clicks on both controls wrote safe output to Windows system clipboard. Markdown had the expected heading; JSON parsed as `context-pack-v1`; neither recorded check contained raw payload or secret markers. No raw clipboard value is recorded.
- Focused DevMemory regression passed: `test_memo_insights.py`, Context Pack builder/golden, and lifecycle-report tests: `15 passed`. Compose was healthy; unauthenticated Memos `auth/me` returned `401`; the read-only lifecycle report exposed aggregates only.
- Phase 10 当时的 verification：focused webhook regression `1 passed`; AI Service full suite and `scripts/verify-devmemo.ps1` both `188 passed` with one existing deprecation warning; `docker compose config --quiet` passed. Serial Web gate passed: `33 files / 149 passed`, build, and project `pnpm lint`. 当时 standalone strict baseline 为 13 项；2026-07-27 Phase 12 接管前复核为 15 项，现已收敛到 0。
- The route-B test Memo was not recreated or deleted. The only new persisted AI state was the one authorized accepted Insight; no SQLite seed, authentication bypass, collection/volume change, public API change, or public-chunk flag change occurred. The four participant answers are recorded safely in [`docs/handoffs/2026-07-20-devmemory-real-feedback-evidence.md`](handoffs/2026-07-20-devmemory-real-feedback-evidence.md).
- Phase 10 的首个受控 gateway 证据切片已完成：`python -m scripts.public_chunk_gateway_contract_smoke` 在进程内模拟受信任网关，对精确 raw JSON HMAC、篡改拒绝、唯一可见范围、disabled/401/422/503、授权去重和脱敏逐项断言。它不启动服务、不访问网络、不输出临时 secret；这是本地 contract evidence，不是部署 gateway 或灰度 rollout 通过。
- Phase 10 contract slice 当时门禁：AI Service `187 passed`；Web `33 files / 149 passed`、build、项目 `pnpm lint` 通过。该切片当时 strict baseline 为 13 项；Phase 12 接管前为 15 项，现已收敛到 0。
- 本地 Chrome 产品验收已通过：Memo 详情页 AI Inbox 的 Context Pack `Copy Markdown` 与 `Copy JSON` 均实际写入 Windows 系统剪贴板。Markdown 为 512 字符并包含标题与 Memo/Insight 来源；JSON 为 1,699 字符、可解析且含两条可追溯来源。浏览器页面未再进入错误边界。
- 复制实现优先使用受用户手势触发的 DOM `execCommand("copy")`，再回退到异步 Clipboard API；复制反馈不再动态替换 SVG 图标，避免先前 Chrome 表面中的 `insertBefore` React 错误。前端回归：`33 files / 149 passed`、TypeScript 与 lint 通过。
- Phase 9f 的 golden parity、只读生命周期诊断和 Context Pack Chrome 复制证据均已完成；Phase 8 `public-chunk-v1` 仍为默认关闭的受控实现，不应在没有可信网关 HMAC/可见范围集成证据时开启。
- 下一窗口入口：[`docs/handoffs/2026-07-20-devmemory-rollout-handoff.md`](handoffs/2026-07-20-devmemory-rollout-handoff.md) 与 [`docs/prompts/NEW_WINDOW_PROMPT.md`](prompts/NEW_WINDOW_PROMPT.md)。

## Phase 8 public-chunk-v1 implementation (2026-07-20)

- Product approval accepted for the independent `POST /api/ai/v1/chunks/search` contract. It is opt-in (`AI_PUBLIC_CHUNK_RETRIEVAL=false` by default) and rolls back by disabling that flag without touching `memo-v1`, the chunk collection, or any volume.
- A trusted gateway must HMAC-sign the raw request body with `AI_PUBLIC_CHUNK_SECRET` in `X-DevMemo-Chunk-Signature`. Its signed `visible_memo_ids` are the enforced Memo-level visibility scope; AI Service does not invent a second Memos authorization system.
- `public-chunk-v1` fixes `memo-chunk-v1`, keeps only the best score per authorized Memo, applies deterministic ordering, and returns a strict metadata allowlist (`source_type`, optional bounded `title`) with no content, webhook payload, secret, or internal fields.
- Contract/API tests: `13 passed`; controlled lifecycle evidence: `11 passed` for delete, chunk replay/idempotence, reject/stale, and accepted-only filtering. AI Service full suite: `186 passed` (one existing deprecation warning). Chrome clipboard acceptance is now separately verified as described above.

## Phase 9f minimum slice (2026-07-20)

- Completed exact cross-language Context Pack golden output: Python and Web now consume the same fixture cases and produce byte-for-byte identical Markdown and canonical compact snake_case JSON.
- Added a local-only lifecycle diagnostic command, `python -m scripts.devmemory_lifecycle_report`, which opens the AI SQLite database read-only and reports only aggregate derived-record/status/version counts.
- Previous Phase 9f verification: AI Service `179 passed` (one existing Starlette/httpx deprecation warning); Web `33 files / 149 passed`; verify script, Compose config, TypeScript, build, lint, and `git diff --check` passed.
- Phase 9f remains in progress only for future product feedback; its cross-language parity, local diagnostic and Chrome clipboard acceptance are complete. Phase 8 public chunk API is implemented but remains disabled by default pending gateway rollout evidence.

## 人工功能检查修复（2026-07-14）

- 已修复本地回环地址 CORS 缺口：Compose 默认同时允许 `localhost:3001` 与 `127.0.0.1:3001`。
- 已记录源码变更后使用 `docker compose up -d --build`，避免 AI Service 复用旧镜像。
- `POST /api/ai/summarize` 现在会为显式 Code Snippet/Bug Report 持久化详情页模板；Memo 保存后的自动处理仍需要配置 Memos Webhook。
- Phase 9 首个垂直切片已完成：`MemoInsight` contract、AI Service SQLite 幂等状态、preview/查询/approve/reject 内部 API，以及 Memo 详情页 AI Inbox 卡片均已落地；当前仍不实现 Phase 8 public chunk API。
- Phase 9 离线验证：AI Service `162 passed`；前端 `136 passed`，TypeScript、build、lint 通过；真实 Compose API 已验证 Bug Report 生成 bug/action、状态批准和版本递增；Playwright 截图 artifact 为 `devmemo-phase9-ai-inbox.png`。
- Phase 9b 已完成：Context Pack v1 contract、纯函数 builder、显式来源/状态校验、同 Memo 去重、确定性排序、Markdown 字符预算和 JSON/Markdown fixture 已落地；AI Service 全量 `174 passed`。
- Phase 9d 已完成：Memo 详情页 AI Inbox 已增加内存 Context Pack preview/copy；复用 `context-pack-v1` 语义，默认当前 Memo + accepted insights，未新增 HTTP、SQLite、Qdrant 或后台 worker。
- Phase 9d 验证：前端全量 `143 passed`；TypeScript、build、lint 通过；Playwright 已验证登录、详情页、approve insight、Markdown/JSON copy、`max_chars` 截断和 390px 窄屏，截图 artifact 为 `devmemo-phase9d-context-pack-desktop.png` 与 `devmemo-phase9d-context-pack-mobile.png`。
- Phase 9e 已完成：新增根目录共享 `contracts/context-pack-v1.json`，Python/Web 测试共同读取；Memo 详情页 Context Pack 只从当前用户可见的 Memos 列表提供显式跨 Memo 选择，默认不扩展来源；删除 Webhook 会清理 AI Service 自有的 note/template/insight 派生状态。
- Phase 9e 验证：AI Service 全量 `175 passed`；前端全量 `147 passed`；TypeScript、build、lint、verify 脚本和 Compose config 通过。撤销联动：只有 accepted insight 进入 pack；reject 会因 React Query 失效自动移除，过期版本仍由 409 拒绝；跨 Memo 查询失败显示不可用提示，不显示原始内容、Webhook payload、secret 或 chunk content。

## 人工验收与问题修复（2026-07-15）

- 真实手动路径已跑通：创建两条 Memo -> 本地 AI webhook -> AI Inbox Accept/Reject -> Context Pack question/预算/来源选择；accepted insight 进入 pack，rejected insight 不进入 pack，跨 Memo 只有显式勾选才进入。
- 修复 `memos/{uid}` 与详情路由 `{uid}` 混用导致的当前 Memo 重复来源；修复取消全部来源后无法重新勾选的问题。
- 修复删除联动遗漏：删除 Memo 的 AI 派生状态清理现在同时删除 SQLite `memo_chunk_index_state`；chunk mode 先删除向量/生命周期再清理 SQLite，避免返回错误的 `index_status=skipped`，并增加 webhook 回归测试。
- 复制验收发现当前 In-App Browser 同时缺少 `navigator.clipboard` 与 `document.execCommand`；现已改为自动选中预览并显示 `Ctrl+C` 手动复制提示，不再把受限环境误报为 copy failure。刷新最新前端后的详情页 DOM 验收已确认提示可见；真实 Chrome 的系统剪贴板仍需单独复验。本轮 CDP 截图调用超时，既有详情页截图 artifact 仍保留；Statsig 外部请求超时与本地应用无关。

更新时间：2026-07-20

## 当前阶段

Phase 0、Phase 1、Phase 2、Phase 2b、Phase 2c、Phase 2d、Phase 3a、Phase 3b、Phase 3c、Phase 3d、Phase 3e、Phase 3f、Phase 3g、Phase 4、Phase 4b、Phase 4c、Phase 4d、Phase 4e、Phase 4f、Phase 4g、Phase 5a、Phase 5b、Phase 5c、Phase 5d、Phase 5e、Phase 5f、Phase 5g、Phase 6、Phase 7、Phase 8、Phase 9a、Phase 9b、Phase 9c、Phase 9d、Phase 9e、Phase 9f 已完成；Phase 10 route B 已完整记录真实本地 Webhook → Insight → accepted Review → Context Pack → Chrome/Windows 复制 → 参与者反馈。public-chunk-v1 仍默认关闭；route A 只有在真实受信任网关、Memos 可见范围映射和回滚条件齐备时才能独立推进。

## 当前事实

- 工作区：H:\DevMemoAI
- 分支：codex/devmemo-ai-mvp
- 协作模式：单 Agent；只使用主工作树，`project4` 下的 Terra/Luna worktree 暂不参与开发
- Memos 基线：v0.29.1
- Go：G:\Go；Go 工作区和缓存：G:\GoWorkspace
- AI Service：FastAPI，默认 deterministic provider
- AI 数据：AI Service 自有 SQLite；不修改 Memos 数据库
- 默认向量存储：InMemoryVectorStore
- 可选向量存储：QdrantVectorStore
- 可选 embedding：FastEmbedEmbeddingProvider，默认不启用、不加载模型；本机已安装依赖用于 smoke
- 索引健康接口：GET `/api/ai/index/health`，默认 memory 路径不连接 Qdrant
- RAG 接口：POST `/api/ai/chat`，当前检索完整 Memo 并返回引用；默认 deterministic + memory 可离线运行
- 检索质量：内部 `RetrievalEvaluator` 提供离线 Recall@K/首个相关结果评估，不改变 chat API
- Chunking 边界：provider-neutral `MemoChunk` 使用 `memo-chunk-v1`/`chunk` metadata；通过显式 `AI_INDEX_MODE=chunk` 接入 Webhook 生命周期，默认不启用
- Chunk 离线评估：`OfflineChunkIndex` 复用 deterministic + memory 与 `RetrievalEvaluator`，可对照完整 Memo 基线，不改变公共 chat API
- Chunk 生命周期：`AI_INDEX_MODE=chunk` 显式启用 `ChunkLifecycleCoordinator`；默认 `memo-v1` 不变，AI SQLite 只持久化 chunk ID 状态
- Chunk store 隔离：chunk Webhook 使用独立 VectorStore；仅显式 `AI_INDEX_MODE=chunk` + `AI_VECTOR_STORE=qdrant` 选择 `QDRANT_CHUNK_COLLECTION`，默认仍为独立 InMemoryVectorStore
- Phase 5f composition：完整 Memo 使用 `QDRANT_COLLECTION`/`memo-v1`，chunk 使用 `QDRANT_CHUNK_COLLECTION`/`memo-chunk-v1`，两者 collection、metadata 和检索源隔离
- 内部 chunk retrieval：`ChunkRetrievalService` 返回独立 `ChunkRetrievalResult`；citation 显式携带 memo/chunk/version/index，原文只进入服务端 context，不进入公共响应
- Qdrant chunk smoke：`python -m scripts.smoke_qdrant --provider deterministic --mode chunk` 已通过；初始/重连 point_count 均为 2，删除后为 1，临时 collection 自动清理
- Chunk health：GET `/api/ai/index/chunk-health` 返回 `memo-chunk-v1`、点数、已登记 Memo/chunk 数量和 SQLite/memory 状态
- Webhook 安全：可选 `AI_WEBHOOK_SECRET` + `X-DevMemo-Signature: sha256=<hex>` HMAC 校验
- Webhook outbox：GET `/api/ai/ops/outbox` 读取状态，POST retry 显式有限重试，默认不启动 worker
- Ops 安全：可选 `AI_OPS_TOKEN` 保护运维 API；公开响应不返回原始 payload，错误摘要最多 240 字符
- Outbox 运维：retention preview 只读，alerts 提供失败/耗尽摘要；清理必须显式确认并写入审计，不自动删除或主动推送
- Phase 5g rollout gate：AI 153 passed；前端 131 passed；TypeScript、build、lint、Compose config 和 Go `go test -p 2 ./...` 通过；Qdrant Server 1.18.2 chunk smoke 通过
- Phase 6 compatibility decision：现有公共 `embedding_id`/`retrieved_count` 继续表示完整 Memo；不启用隐式 chunk mode，不新增未定义公共 chunk endpoint，未来必须使用版本化 contract
- Phase 7 public API proposal：提出 `POST /api/ai/v1/chunks/search` / `public-chunk-v1`，默认关闭，固定 memo-chunk-v1，同 Memo 保留最高分 chunk，未新增 HTTP 行为
- Phase 8 implementation gate：已获明确批准并实现独立 `public-chunk-v1` 路由；默认关闭，要求受信任网关 HMAC 签名可见 Memo 范围，不改变公共 chat 或完整 Memo collection
- Phase 9e shared fixture：`contracts/context-pack-v1.json` 是 Python/Web 测试的共同输入；生产代码仍保持 provider-neutral builder/adapter 双边界。
- Phase 9e permission/deletion：跨 Memo 选项来自 Memos 当前用户可见的 `useInfiniteMemos` 结果，只有用户勾选才加入；删除 Webhook 调用 `delete_memo_ai_state` 清理 `ai_notes`、`memo_templates`、`memo_insights` 和 `memo_chunk_index_state`，不触碰 Memos 原文或公共 chat。
- Phase 9a DevMemory Loop：`MemoInsight` 统一包含 `insight_id`、`memo_id`、`insight_type`、`title`、`summary`、`confidence`、`status`、`source_refs`、版本和审计时间；deterministic parser 只为 Code/Bug/plain Memo 生成有限候选，不做自由发挥式知识图谱
- Phase 9a SQLite：AI 自有 `memo_insights` 表按 `(memo_id, insight_type)` 幂等 upsert；语义变化会重置为 pending 并递增版本，approve/reject 必须携带当前版本，过期更新返回 409
- Phase 9a API/UI：新增内部 preview、Memo insight 查询和显式状态变更 API；Memo 详情页 AI Inbox 支持空、失败、窄屏和 pending approve/reject；原文 content 不进入公共 citation 或卡片响应
- Phase 9b Context Pack：`ContextPackRequest` 只接受显式 Memo/accepted insight IDs，拒绝未知、pending/rejected 和隐式 Memo 扩展；`build_context_pack` 只消费安全 title/summary 与 `source_refs`
- Phase 9b bounded output：输出固定 `context-pack-v1`、可复制 Markdown、可序列化 JSON、唯一 source 列表和显式 `max_chars`/`max_items` 截断原因；不连接 HTTP、Qdrant、公共 chat 或外部数据源
- Phase 9c integration gate：推荐只在当前 Memo 详情页 AI Inbox 增加“复制 Context Pack”；默认当前 Memo，跨 Memo 必须显式选择；命令面板和独立页面暂不采用
- Phase 9c permission/revocation：仅当前用户可见 Memo 与 accepted insight 可进入；pending/rejected、删除 Memo、撤销 insight、版本过期和不可见来源必须排除；Context Pack 不持久化
- Phase 9c interaction proposal：Markdown 为主复制格式，JSON 为可选复制格式；展示 sources、截断提示、空态、失败态和窄屏行为；不显示 raw content/Webhook payload/secret/chunk content
- Phase 9d UI：`web/src/features/ai/AiMemoContextPack.tsx` 复用现有 insight 查询，在浏览器内调用 provider-neutral `buildContextPack` 镜像 contract；默认仅当前 Memo，accepted insight 可单独勾选，跨 Memo 当前不自动发现也不提供隐式入口
- Phase 9d 边界：AI Service 查询失败显示 failure，零 accepted insight 或用户清空来源显示 empty；pending/rejected 不进入选择项，Memo title/insight summary/source_refs 之外的 raw content、Webhook payload、secret、chunk content 不进入 pack
- 项目结构问题：`AI Inbox` 是详情页 feature 而非独立模块；Python canonical builder 与 Web contract adapter 目前存在双实现，需后续共用 fixture 防止语义漂移；`graphify-out` 仍把 Inbox 解析为 Memos `store/inbox.go`，未覆盖新 AI feature，结构查询有命名冲突
- 文档同步：2026-07-14 已按实际仓库目录刷新 README、架构、API、开发、OSS 采用和结构边界文档；Phase 5f/5g 事实已同步

## Phase 4 已完成

- 新增 provider-neutral `RetrievalService`：问题 embedding -> VectorStore.search -> 结构化 citations/context。
- 当前以一个完整 Memo 为一个检索单元；索引派生 metadata 保存原文供上下文组装，API 引用会剥离内部 `content` 字段。
- 新增 POST `/api/ai/chat`，接收 `question` 和 `limit`，返回 `answer`、`citations`、`provider`、`retrieved_count`。
- deterministic provider 返回可复现的引用式离线答案；OpenAI/Ollama 复用现有 LLM adapter。
- 空知识库返回明确空结果；非法 limit 返回 422；检索不可用返回 503；LLM 失败返回 502。

## Phase 4b 已完成

- 新增 provider-neutral `app/services/webhook_security.py`，使用标准库 HMAC-SHA256 校验原始 Webhook body。
- `AI_WEBHOOK_SECRET` 未配置时保持兼容放行；显式配置后缺失、错误或篡改签名返回 401。
- 签名校验位于 Webhook 业务处理前，不改变有效请求和默认 `code=0` 契约；未修改 Memos API、数据库或 Proto。
- Docker Compose 暴露空默认的 `AI_WEBHOOK_SECRET`/`AI_OPS_TOKEN` 配置，不增加默认 CPU、网络或模型负担。

## Phase 4c 已完成

- AI Service SQLite 新增兼容 `webhook_events` 表，记录 `event_id`、`event_type`、`payload`、`status`、`attempts`、`last_error`、`created_at`、`updated_at`。
- Webhook 优先入队；显式 `eventId` 使用原值，没有 eventId 时使用原始 body SHA-256 派生稳定 ID。
- 重复 event ID 不重复执行摘要、模板或索引；业务异常记录 `failed`，仍返回 `code=0`。
- 新增 GET `/api/ai/ops/outbox?status=&limit=` 运维读取 API；不引入后台 worker、Redis、Celery 或新依赖。

## Phase 4d 已完成

- `webhook_events` 通过兼容 SQLite 补列增加 `max_attempts`，默认总尝试上限为 3；旧表和旧数据保留。
- 新增 POST `/api/ai/ops/outbox/{event_id}/retry`，仅允许 `failed` 事件；重试准备在 SQLite 事务中原子切换为 `pending`。
- 重试成功转为 `processed` 并清除 `last_error`；再次失败保持 `failed` 并递增 `attempts`；达到上限返回 409。
- GET outbox 增加 `by_status` 和最多 5 条 `recent_errors`，不引入后台 worker、定时任务、外部队列或观测依赖。

## Phase 4e 已完成

- 新增可选 `AI_OPS_TOKEN` 和 `X-DevMemo-Ops-Token`，配置后保护 outbox GET/retry POST；未配置时保持本地开发兼容。
- 公开 outbox item 移除原始 Webhook payload；SQLite 内部 payload 保留，不影响 retry 编排。
- `last_error` 和最近错误摘要归一化为单行并截断到 240 字符；认证失败返回 401。
- 未引入认证服务、Redis、Prometheus、后台 worker 或前端运维 UI。

## Phase 4f 已完成

- 新增 GET `/api/ai/ops/outbox/retention-preview`，按 `updated_at` 预览超过阈值的 `processed/failed` 终态事件；默认 30 天、最多 100 条，只读不删除。
- 新增 GET `/api/ai/ops/alerts`，返回 `failed_count`、`exhausted_count` 和最多 5 条 warning/critical 摘要；继续受 `AI_OPS_TOKEN` 保护。
- alerts/preview 均不返回 payload、secret 或未截断错误；不启动 worker、不推送外部告警、不修改任何 Qdrant/AI volume。

## Phase 4g 已完成

- retention preview 返回固定 `cutoff`、`preview_limit` 和 `candidate_ids`，供后续批准请求绑定。
- 新增 POST `/api/ai/ops/outbox/retention-cleanup`；默认 `dry_run=true`，只有 `confirm=true` 且 `dry_run=false` 才执行。
- 清理在 SQLite 事务中重新校验完整 preview 集合、cutoff 和 `processed/failed` 终态；pending、集合外 ID 或数据变化整批拒绝。
- 新增 `webhook_cleanup_audits` 和 GET `/api/ai/ops/outbox/cleanup-audits`；记录 approval_id、actor 摘要、cutoff、候选数、删除数和执行时间，不保存 ops secret。
- 相同 approval_id 的重复执行幂等返回；清理只处理 AI Service 自有 webhook_events，不触碰 Memos、ai_notes、memo_templates、原始 Markdown 或 Qdrant volume。

## Phase 5a 已完成

- 选择离线检索评估作为最小切片，暂不改变当前“一整个 Memo 一个向量”的索引契约。
- 新增 provider-neutral `RetrievalEvaluationCase`、`RetrievalEvaluationResult` 和 `RetrievalEvaluator`。
- 支持 Recall@K、命中 Memo ID、首个相关结果排名和批量评估；不连接网络、不依赖 FastEmbed/Qdrant SDK。
- deterministic + memory 实际检索契约和评估器均有 unit/contract tests；未新增公共 API。

## Phase 5b 已完成

- 新增 provider-neutral `MemoChunk` 和 `chunk_memo`，按 Markdown 换行边界或固定字符上限切分，并保留源 Markdown 字符序列。
- 稳定 chunk ID 使用 Memo ID、`index_version` 和 chunk position；同一位置更新可复用 ID，缩短内容时可显式计算 stale IDs 删除。
- metadata 明确包含 `source_type=memo_chunk`、`index_mode=chunk`、`index_version=memo-chunk-v1`、chunk 序号/总数和派生 content。
- 覆盖空内容、超长内容、更新、删除、重复 ID、metadata 复制和非法参数；没有接入 Webhook、Qdrant、FastEmbed 或默认 Compose。

## Phase 5c 已完成

- 新增 provider-neutral `OfflineChunkIndex`，使用 chunk ID 作为试验索引 embedding ID，复用现有 VectorStore 和 RetrievalService。
- chunk citation 明确保留 `memo_id`、`chunk_id`、`chunk_index`、`index_version` 和服务端上下文；公共 `POST /api/ai/chat` 契约未改变。
- 支持完整 Memo 与 chunk 试验索引使用同一 `RetrievalEvaluator` 做 Recall@K/首个命中排名对照；仅访问 deterministic + memory，不下载模型或连接 Qdrant。
- 覆盖 upsert、更新后的显式 stale chunk delete、重复/空 chunk 和 citation/context contract；未接入默认 Webhook 或生产索引。

## Phase 5d 已完成

- 新增 provider-neutral `ChunkLifecycleCoordinator`，支持 chunk create/update/delete；更新先 upsert 当前 chunk，再删除同一 `memo-chunk-v1` 版本的旧尾部 chunk。
- 新增 AI Service 自有 SQLite `memo_chunk_index_state`，只记录 `memo_id`、`index_version`、`chunk_ids` 和更新时间，用于进程重启后的生命周期清理；不保存或替代原始 Markdown。
- 新增 `AI_INDEX_MODE=memo|chunk`，默认 `memo`；只有同时开启 `AI_INDEX_ON_WEBHOOK=true` 和 `AI_INDEX_MODE=chunk` 时 Webhook 才使用 chunk 路径。
- chunk Webhook 覆盖 create/update/delete、空内容清理、eventId 幂等和失败降级；完整 Memo `memo-v1`、`POST /api/ai/chat`、Webhook `code=0` 和默认 Compose 契约保持不变。
- chunk lifecycle 当前只验证 deterministic/provider-neutral + 独立 memory store；未把 chunk 向量接入 Qdrant，也未改变公共 chat 的完整 Memo 检索源。

## Phase 5e 已完成

- 新增 provider-neutral `ChunkIndexStateStats` 和 `ChunkIndexHealth`，同时观测 chunk VectorStore 点数与 SQLite 登记的 Memo/chunk 数量。
- 新增只读 GET `/api/ai/index/chunk-health`，显式返回 `index_mode=chunk`、`index_version=memo-chunk-v1`、provider、dimension、point_count、tracked_memos、tracked_chunks、state_backend 和降级 detail。
- health 不触发索引、不扫描原始 Markdown、不改变完整 Memo `GET /api/ai/index/health` 或 `POST /api/ai/chat`；SQLite 状态损坏/不可用会返回 `status=degraded`，不静默报告 ready。
- 覆盖空状态、create/update/delete 后计数、版本隔离、SQLite 重启读取和 HTTP contract；默认 deterministic + memory、不访问网络。

## Phase 3c 已完成

- 新增 `FastEmbedEmbeddingProvider`，只在 adapter 内导入 `fastembed.TextEmbedding`。
- 新增 `requirements-fastembed.txt`，固定 `fastembed==0.8.0`；默认 requirements 不增加模型/ONNX 网络依赖。
- 增加 `AI_EMBEDDING_PROVIDER=deterministic|fastembed`、`AI_FASTEMBED_MODEL` 和 `AI_FASTEMBED_DIMENSION`。
- 默认仍使用 8 维 deterministic provider；显式 fastembed 模式检查模型输出维度并与 VectorStore 维度匹配。
- 新增 `MemoIndexDocument`/`index_memo` 索引边界；当前一个完整 Memo 对应一个向量，chunking 延后。
- POST `/api/ai/embed` 保持响应契约，新增索引 metadata：`source_type=memo`、`index_version=memo-v1`。

## Phase 3d 已完成

- 新增 `AI_INDEX_ON_WEBHOOK`，默认 `false`，Compose 默认不触发向量索引。
- 开启后，Memo created/updated 通过 `MemoIndexDocument` 做稳定 ID 幂等 upsert。
- deleted 事件按 Memo UID 删除对应向量；缺少 UID 时安全返回 `index_status=skipped`。
- 索引失败不会阻断摘要、模板持久化或 Webhook `code=0` 响应，返回 `index_status=failed`。
- Webhook 非空 Memo 返回 `index_status=indexed|skipped|failed`；删除返回 `deleted|skipped|failed`。

## Phase 3e 已完成

- Docker Desktop Linux Engine 已启动，Compose Qdrant 服务在 `http://127.0.0.1:6333` 正常响应。
- 在 ai-service 虚拟环境安装 `qdrant-client==1.18.0`；Qdrant Server smoke 使用 `qdrant/qdrant:latest`，当前服务端返回 1.18.2。
- 真实验证了 collection 创建、384 维 FastEmbed 向量 upsert、`query_points` search、payload 映射和 delete。
- FastEmbed + Qdrant smoke 返回 `fastembed-1` 最近结果，删除后该向量不再可检索；临时 collection 已清理。
- 新增 `ai-service/scripts/smoke_qdrant.py`，默认 FastEmbed，可切换 deterministic，使用模块方式运行。
- 安装 qdrant-client 后，缺失可选依赖测试改为通过模块注入模拟，不依赖卸载本机包。

## Phase 3f 已完成

- Compose 为 AI Service 增加可选 `/app/model-cache` volume；`AI_FASTEMBED_CACHE_DIR` 可配置 FastEmbed 模型缓存目录。
- Compose 默认设置缓存目录为 `/app/model-cache`，但 provider 默认仍为 deterministic，因此不会日常下载或加载模型。
- Qdrant 数据 volume `devmemoai_qdrant-data` 确认挂载到 `/qdrant/storage`，没有执行 `down -v` 或删除 volume。
- 使用 `devmemo_phase3f_persistence_20260713` 临时 collection 写入 `persist-1`，执行 `docker compose restart qdrant` 后仍能检索到同一 embedding_id、memo_id 和 metadata；验证后已清理临时 collection。
- FastEmbed 可选缓存目录 smoke 已通过，`H:\DevMemoAI\ai-service\model-cache` 约 64.07 MB，并在 `HF_HUB_OFFLINE=1` 下成功加载 384 维模型。
- 首次直接迁移下载曾因 Hugging Face 代理 `RemoteProtocolError` 中断，未将网络问题伪装成代码成功；复用已验证本地缓存后完成离线验证。

## Phase 3g 已完成

- 新增只读 `GET /api/ai/index/health`，返回 provider、available、dimension、status、collection、point_count 和 detail。
- InMemoryVectorStore 本地返回 `ready`，不会连接 Qdrant；QdrantVectorStore 将 SDK 查询异常转换为 `available=false、status=unavailable`。
- FastEmbed 模型初始化错误现在包含 cache_dir 和修复提示，缓存损坏不被伪装为成功。
- Qdrant `latest` 已固定到已验证的 Server 1.18.2 镜像 digest `sha256:75eab8c4...`。
- 增加 Qdrant health、不可用降级、FastEmbed cache 错误和 API contract tests；未修改 Memos 核心。

## Phase 3b 已完成

- 新增 QdrantVectorStore adapter，实现现有 VectorStore Protocol 的 upsert、query_points search、delete。
- Qdrant point 使用稳定 UUID 映射，原始 embedding_id、memo_id 和 metadata 保存在 payload。
- 增加维度、collection、payload 和 optional dependency 错误边界。
- 新增 requirements-qdrant.txt，固定 qdrant-client 1.18.0；默认 requirements 不增加网络依赖。
- 新增 AI_VECTOR_STORE=memory|qdrant 配置，默认 memory。
- AI 容器不再 depends_on Qdrant/Ollama，默认启动不依赖外部 AI/向量服务。
- Qdrant fake client contract tests 不访问网络。

## 验证状态

~~~text
AI Service full pytest             174 passed
FastEmbed fake/model tests          6 passed
Provider/index targeted tests      13 passed
frontend full tests                143 passed
frontend TypeScript/build          PASS
Go full test -p 2 ./...            PASS (store/test 168.864s)
verify-devmemo.ps1                 PASS / DEVMEMO_VERIFY_OK
docker compose config              PASS
Qdrant chunk smoke                 PASS / QDRANT_CHUNK_SMOKE_OK
Qdrant volume restart              PASS / collection and point recovered
FastEmbed cache-dir smoke           PASS / offline 384-dim load
Qdrant health smoke                PASS / green collection status
Index health contract tests         PASS / memory and degraded qdrant
git diff --check                   PASS
pnpm lint                          PASS
~~~

## 网络与环境证据

- 当前 ai-service 虚拟环境已安装 qdrant-client 1.18.0 和 fastembed 0.8.0；FastEmbed 模型缓存约 64.07 MB。
- Docker Desktop Linux Engine 已运行；Qdrant 服务端返回 1.18.2。
- FastEmbed 真实模型下载/推理、FastEmbed+Webhook create/update/delete smoke 和 FastEmbed+Qdrant collection/upsert/search/delete smoke 均已通过。
- fastembed 和 qdrant-client 的版本、许可证、维护风险和替换边界记录在 docs/DECISIONS.md。

## 已知未完成项

- 当前默认 memory 索引为进程内存，服务重启后不保留。
- Compose Qdrant volume 重启持久化已验证；FastEmbed 可选缓存目录已验证，默认 Compose 仍不加载模型。
- Qdrant health API、不可用降级和 FastEmbed 缓存损坏错误边界已验证；镜像已固定到已验证 digest。
- Webhook 默认不触发向量索引；开启 `AI_INDEX_ON_WEBHOOK=true` 后才会触发。
- FastEmbed smoke：首次加载约 23.48 秒，单条 embedding 约 0.06 秒，返回 384 维；项目缓存目录约 64.07 MB。
- 当前 RAG 只检索完整 Memo，默认 memory 为进程内存；服务重启后不保留索引。
- Phase 5e 已增加 chunk health/status；Phase 5f/5g 已完成独立 collection/config/composition、内部 chunk retrieval、真实 Qdrant health/persistence smoke 和完整 rollout gate。chunk 仍未替换公共 `POST /api/ai/chat` 的完整 Memo 检索。
- 当前 outbox 提供显式有限重试、基础状态计数、ops token、保留预览、告警轮询和显式清理审计；没有自动 worker、主动告警推送或定时清理。
- Phase 9d Web lint/build/typecheck 已通过；当前 Context Pack 逻辑只在 Web 内存运行，不改变 AI Service API。

## 下一步

Phase 8 public chunk API 仍等待明确批准，不改变现有公共 chat。Phase 9a/9b/9c/9d 已完成；下一步执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 9e Context Pack product acceptance，重点是共享 fixture、权限感知跨 Memo 显式选择和删除/撤销联动。
