# DevMemo AI 项目结构与 Phase 12 接管交接

更新时间：2026-07-27

## 接管结论

从 `H:\DevMemoAI` 主工作树继续，分支为 `codex/devmemo-ai-mvp`。本次结构核验的干净基线提交为 `dd26feb feat(web): show Context Pack copy readiness`，当时本地相对 origin ahead 12；本交接会形成后续独立文档提交，仍不 push。

Phase 11 的实现、验证和 Chrome 认证阻塞不在本文重复，直接读取：

- `docs/handoffs/2026-07-27-context-pack-copy-readiness-handoff.md`
- `docs/PROJECT_STATUS.md` 顶部
- `docs/prompts/NEXT_STAGE_PROMPT.md`

下一执行切片是 Phase 12 Web strict TypeScript baseline。不要重新设计架构，也不要重跑 Phase 10 route B。

## 当前实时结构

```text
H:\DevMemoAI
├── cmd/ server/ store/ internal/ proto/  # Memos Go 核心、权限和原始 Memo 事实源
├── web/                                  # Memos React 前端
│   └── src/features/ai/                  # 当前 DevMemo AI 产品入口
├── ai-service/                           # 独立 FastAPI 派生服务
│   ├── main.py                           # HTTP 组合入口
│   ├── database.py                       # AI 自有 SQLite
│   └── app/
│       ├── domain/                       # provider-neutral contract/model
│       ├── services/                     # 用例编排
│       └── adapters/                     # memory/FastEmbed/Qdrant 等实现
├── contracts/                            # context-pack-v1、public-chunk-v1 fixtures
├── integrations/ scripts/                # 集成与本地验证
├── docs/                                 # 状态、路线、API、ADR、handoff、prompt
└── docker-compose.yml                    # 默认 Memos + AI；Qdrant/Ollama 显式 profile
```

### Memos 核心

`cmd/`、`server/`、`store/`、`internal/`、`proto/` 与通用 `web/` 仍是上游 Memos 产品边界。原始 Memo、用户身份、可见范围、删除与权限判断以 Memos 为准。当前阶段不把 AI 字段写入 Memos 数据库，也不修改 server/store/proto 来承载 AI 派生状态。

### AI Service

- `ai-service/main.py` 暴露 health、index health、summary、insight preview/query/status、完整 Memo chat、AI note/template、ops outbox、Memos webhook，以及默认关闭的 `POST /api/ai/v1/chunks/search`。
- `ai-service/database.py` 只保存 AI 派生的 notes、templates、insights、chunk index state 与 webhook/outbox 状态；不成为原始 Memo 或权限事实源。
- `ai-service/app/domain/` 固定 Context Pack、MemoInsight、embedding、chunking、retrieval 和 evaluation 契约。
- `ai-service/app/services/` 编排 parser、insight、indexing、retrieval、public chunk、security 与 lifecycle。
- `ai-service/app/adapters/` 承载 memory、FastEmbed、Qdrant 等可替换实现。默认仍是 deterministic + memory。

### Web 产品入口

`web/src/components/MemoView/MemoView.tsx` 直接挂载：

- `AiMemoSummary`
- `AiMemoTemplate`
- `AiMemoInsights`
- `AiMemoContextPack`

`web/src/features/ai/` 内的 `api.ts`/`hooks.ts` 连接 AI Service，`contextPack.ts` 是 provider-neutral Web adapter。Context Pack 继续只在浏览器内存生成，使用显式可见 Memo、accepted insights 和安全 title/summary/source refs；不落 SQLite、不读取 Qdrant、不启动 Agent/worker。

### Compose 与资源边界

- 默认服务：`memos`、`ai-service`。
- 显式 profiles：`qdrant`、`ollama`。
- CPU 上限：Memos `0.75`，AI Service `0.25`；Qdrant `0.5`，Ollama `1.0`。
- 默认：`AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、`AI_VECTOR_STORE=memory`、`AI_PUBLIC_CHUNK_RETRIEVAL=false`。
- Memos 的 `--allow-private-webhooks` 只服务于本机 Docker 私网 webhook，不代表 public-chunk gateway rollout。

## Graphify 证据边界

`graphify-out/graph.json` 存在，但最后更新时间为 2026-07-12。查询可识别 Web `main.tsx`、Auth/Instance context 和通用开发入口，却没有近期 `AiMemoInsights`、`AiMemoContextPack` 与 Phase 10/11 结构。因此：

- 现有 graphify 只作为历史索引。
- 当前结构以实时 `rg --files`、源码引用、`docs/structure.md` 和本 handoff 为准。
- 不要因图谱中的 “Inbox” 节点推断当前 AI Inbox；若需要可靠图查询，应把 graphify update/rebuild 作为独立维护任务。

## Phase 12 strict TypeScript 现场基线

2026-07-27 在 `web/` 串行运行 `pnpm exec tsc --noEmit --pretty false`，得到 15 个错误：

| 类别 | 数量 | 当前表现 |
| --- | ---: | --- |
| `@tanstack/query-devtools` | 6 | 缺 `solid-js` 4 项、`@solid-primitives/storage` 2 项 |
| `goober` | 1 | ESM target 下 export assignment 不兼容 |
| `mermaid` | 1 | 缺 `type-fest` declaration |
| `react-leaflet-cluster` | 2 | Leaflet namespace 缺 cluster 类型 |
| `react-leaflet` | 4 | 无法解析 `@react-leaflet/core/lib/context` |
| `src/types/view.d.ts` | 1 | 未定义 `FunctionType` |

项目 `pnpm lint` 使用 `tsc --noEmit --skipLibCheck`，Phase 11 已验证通过；独立 strict gate 才暴露上述 baseline。Phase 12 必须修根因，不得通过全局 `skipLibCheck`、关闭 strict、宽泛 `any` 或 `@ts-ignore` 制造通过。

## Phase 12 边界与执行顺序

1. 先读取 `docs/prompts/NEXT_STAGE_PROMPT.md`，保存错误分类并检查 `tsconfig`、`src/types/view.d.ts` 与相关 package declarations。
2. 首个切片不新增或升级依赖、不改 lockfile；若依赖版本是唯一根因，停止在准确诊断和最小升级提案。
3. 不改变运行时行为、Context Pack golden、Memos 核心、AI Service API、公共 chat、public-chunk contract、collection 或 volume。
4. 不需要启动 Docker、Chrome、Qdrant 或 Ollama；不创建/修改 Memo 或 Insight，不提取 token，不绕过认证。
5. 验证顺序：strict TypeScript → 受影响定向测试 → 串行 Web vitest/build/lint → Compose config → `git diff --check`。
6. 完成后同步状态、变更、交接和 Prompt，创建独立 commit；不自动 push。

## 建议 skills

- `incremental-implementation`：把 15 个错误按声明来源分组，小步修复并逐组复验。
- `source-driven-development`：只有在必须核对 TypeScript/第三方包导出契约时使用官方文档与包内声明。
- `code-review-and-quality`：提交前检查是否用 suppressions 掩盖错误或意外改变运行时。
- `graphify`：仅在明确决定重建/更新结构图时使用；不要把当前旧图当事实源。
