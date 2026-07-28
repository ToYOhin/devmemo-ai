# DevMemo AI 结构复核与公开发布接管记录（2026-07-28）

> 状态更新：本文件记录 GHCR 收尾前的结构与发行快照。独立 Container package 已随后设为 public，且未登录 Docker 客户端已验证 `stable` 的 `linux/amd64`、`linux/arm64`、`linux/arm/v7` manifest。当前权威接管记录为 [`2026-07-28-ghcr-public-closeout-handoff.md`](2026-07-28-ghcr-public-closeout-handoff.md)。

## 接管结论

本次结构结论以 `H:\DevMemoAI` 的实时源码、Compose、现行文档和 GitHub 只读状态为准。`graphify-out/graph.json` 最后一次图谱更新停留在 2026-07-12，查询仍偏向旧的 Memos attachment/scheduler 节点，且未覆盖 AI Inbox 与 Context Pack；它只能作历史导航，不能作为当前结构事实源。

唯一开发入口是 `H:\DevMemoAI` 主工作树。不要在 `project4` 下的历史 Terra/Luna worktree 并行操作。

```text
Memos Go server/store/proto ── Memo 原始数据、身份与权限事实源
          │
          ├── Webhook（显式配置、默认不索引）
          ▼
FastAPI AI Service ────────── AI 派生 SQLite、insight/index/chunk 状态
          │
          ├── deterministic + memory（默认）
          └── FastEmbed/Qdrant（显式 adapter/profile）
          ▲
React MemoView ────────────── AiMemoTemplate / AiMemoInsights /
                                AiMemoContextPack / AiMemoSummary
```

## 已复核的源码边界

- `cmd/`、`server/`、`store/`、`internal/`、`proto/` 是上游 Memos 核心表面。Memos Go server/store/proto 继续是完整 Memo、用户身份和权限的唯一事实源。
- `ai-service/main.py` 是独立 FastAPI 组合入口；`ai-service/database.py` 只保存 AI 派生 SQLite 状态（AI notes、templates、webhook/outbox、insight 和 chunk state），不写回 Memos 原始数据。
- `ai-service/app/domain/` 定义 provider-neutral 模型与 contract；`app/services/` 承担索引、检索、insight、Context Pack 与安全流程；`app/adapters/` 隔离 deterministic/FastEmbed 和 memory/Qdrant。完整 Memo 使用 `memo-v1`，chunk 使用独立的 `memo-chunk-v1` 与 collection/state。
- `web/src/components/MemoView/MemoView.tsx` 只在 Memo 详情页嵌入 `AiMemoTemplate`、`AiMemoInsights`、`AiMemoContextPack`、`AiMemoSummary`；当前没有独立全局 AI Inbox。
- `web/src/features/ai/contextPack.ts` 在浏览器内存生成 provider-neutral `context-pack-v1`。它只接收显式可见 Memo、accepted insight 及安全 title/summary/source refs；不携带 raw memo content、Webhook payload、secret 或 chunk content，不写 SQLite、不连接 Qdrant、不启动 Agent/worker。

## 不可改变的默认与安全边界

- 默认：`AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、`AI_VECTOR_STORE=memory`、deterministic provider。
- `AI_PUBLIC_CHUNK_RETRIEVAL=false` 必须保持关闭。`POST /api/ai/v1/chunks/search` 已有 public-chunk-v1 contract，但 route A 仍缺真实受信任 gateway、Memos 可见范围映射和只关闭 flag 的回滚证据；不扩展浏览器签名。
- 默认 Compose 受低 CPU 约束：Memos `0.75` CPU 和 `GOMAXPROCS=1`，AI Service `0.25` CPU 且数值线程为 `1`；Qdrant 与 Ollama 只能用显式 profile 启动。
- 默认 `docker-compose.yml` 不放行 Memos 私网 Webhook。`docker-compose.local-webhook.yml` 仅供受控本地开发显式叠加，不能用于公共/多用户部署。

## 产品阶段与证据状态

- Phase 10 route B 已完成真实本地 `Capture → Insight → accepted Review → bounded Context Pack → Chrome/Windows Markdown/JSON copy → participant feedback`。不要重复该路径，也不要把历史证据当作新的验收。
- Phase 11 的 Web copy readiness 已实现并通过自动化门禁：items/sources/characters 预算摘要、两种格式一致的 copied 状态、`aria-live` 反馈和 pack 变化后的旧状态清理。由于当前 Chrome profile 没有有效 Memos 登录态，真实详情页和系统剪贴板复核仍是“未验证”，不能写成 pass，也不能从 SQLite/token 存储绕过认证。
- Phase 12 已将独立 strict `tsc --noEmit` 从 15 个既有声明错误收敛至 0；Phase 13 将项目 lint 固定为 `tsc --noEmit && biome check src`。两者均未改变运行时行为。

## 公开发布状态（实时复核）

- 仓库为公开：<https://github.com/ToYOhin/devmemo-ai>。
- 稳定 GitHub Release [`v0.1.0`](https://github.com/ToYOhin/devmemo-ai/releases/tag/v0.1.0) 已发布，不是 draft/prerelease；包含六个原生二进制资产及 `checksums.txt`。Windows x64 ZIP 的 SHA-256 已低负载复核为 `fbb406355fdae63707585d59557374e51064be40bd8496bd26cf9cd5b40b054f`，解压后的 `devmemo-ai.exe --help` 成功。
- GitHub private vulnerability reporting 已启用（API 返回 `enabled=true`）。
- 已有远程 workflow 证据：PR #1 的 Backend、Frontend、AI Service 门禁为绿；稳定 release workflow 已完成并产出资产与多架构镜像 manifest。不要因本次仅文档工作重跑高 CPU 全量门禁。

### 唯一尚未闭环的发行可用性项

独立授权的 GHCR Container package `ghcr.io/toyohin/devmemo-ai` 仍为 private；未登录 Docker 的

```powershell
docker buildx imagetools inspect ghcr.io/toyohin/devmemo-ai:stable
```

返回 401。仓库公开、GitHub Release 发布和 private vulnerability reporting 启用并不会自动公开该 package。当前 CLI OAuth 没有 `read:packages` / `write:packages`，不得用个人 OAuth token 替代 workflow token 或将长效 token 写入仓库。

维护者需要使用有 Packages 管理权限的 GitHub 登录会话，手动在 <https://github.com/ToYOhin/devmemo-ai/pkgs/container/devmemo-ai/settings> 将 package visibility 设为 **Public**。随后只做匿名 `imagetools inspect` 复核，确认 stable manifest 含 `linux/amd64`、`linux/arm64`、`linux/arm/v7`；不要重打 tag、重发 release 或改动产品配置。完成后更新发布文档并按用户明确授权提交/推送。

## 新窗口的最小读取顺序

1. 本文件。
2. `docs/PROJECT_STATUS.md` 顶部与 `docs/HANDOFF.md` 顶部。
3. `docs/structure.md` 的结构与边界段落；按任务定向查询 `docs/roadmap.md`、`docs/DECISIONS.md`、`docs/api.md`、`docs/oss-adoption.md`，不要一次加载历史 Phase 文档。
4. `docs/release-preflight.md` 和 `docs/prompts/NEXT_STAGE_PROMPT.md`。
5. `git status --short --branch`、`git log --oneline -8`；涉及发布时再只读核验 `gh repo view`、`gh release view` 和 GHCR 匿名 inspect。

## 建议技能（按需）

- `graphify`：仅用于定位或后续明确授权的图谱维护；现有图谱过期，结论必须回到实时源码和 `docs/structure.md`。
- `gh-fix-ci`：仅当真实 GitHub CI 失败时，用于读取并修复该失败。
- `chrome:control-chrome`：仅在用户已正常登录 Memos 且明确选择 Phase 11 只读复核时使用；不得提取或重置凭据。

## 相关权威文档

- `docs/structure.md`：目录、运行时与类型兼容层边界。
- `docs/roadmap.md`：Phase 10–13 完成态及受控下一选择。
- `docs/DECISIONS.md`：ADR-043、ADR-051 至 ADR-056 的安全、资源与发布决策。
- `docs/release-preflight.md`：公开发布与镜像验收清单。
- `docs/handoffs/2026-07-28-public-release-handoff.md`：公开稳定版的原始发布证据。
