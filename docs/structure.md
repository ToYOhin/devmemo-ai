# DevMemo AI 项目结构与边界

当前范围见 [项目状态](project-status.zh-CN.md)，推进顺序见 [整体路线](roadmap.md)。
本文只记录当前框架与归属，不重复 PR 历史和测试计数。

## 顶层归属

```text
DevMemo AI
├── cmd/memos/             # Go 入口、Windows 安装/卸载、启动参数
├── server/router/         # frontend/fileserver/MCP/API 与认证 AI BFF
├── store/                 # Memos 权威数据、可见性、源端 lifecycle outbox
├── internal/aiagent/      # 委托契约、限时 AI client、rehydration authority
├── internal/version/      # 内嵌版本与 commit
├── proto/                 # Memos API/生成代码，不作为 AI 派生存储
├── web/                   # React/TypeScript 客户端
├── ai-service/            # FastAPI + AI 自有 SQLite 派生状态 sidecar
├── contracts/             # Go/Python/Web 共用 Provider-neutral fixture
├── integrations/memos/    # Webhook 集成说明
├── scripts/               # 构建、低资源验证、显式演示/Provider smoke
├── .github/workflows/     # Go/Windows、Web、Python、Proto、Canary、Release
└── docs/                  # 状态、路线、契约、开发、运维、发布
```

`build/`、`.devmemo-local/`、`graphify-out/` 是忽略的本地产物，不属于运行时或公共交付。
历史图谱不能覆盖当前源码。此次整理不移动运行时目录，不修改 API 或数据模型。

## 请求与数据流

```text
Browser
  -> same-origin Memos BFF: auth + current visibility + bounded request
  -> signed internal AI request
  -> FastAPI composition -> domain/services -> provider/storage adapters
  -> validated/redacted answer or creator-bound Markdown artifact
```

Memos 是正文、身份、可见性与源端 mutation 的唯一权威。AI Service 保存派生摘要/模板/
insight、索引 ledger、AgentRun metadata/artifact 和加密 Provider 配置；不能成为第二套
身份/权限或 Memo 正文库。run metadata 不保存原始 prompt/secret，派生报告由独立 artifact
store 管理。Context Pack 只在浏览器内存中生成，不写回 Memo 或 AI SQLite。

## 关键实现与测试归属

| 功能 | 实现入口 | 相邻测试 |
| --- | --- | --- |
| Windows 安装器 | `cmd/memos/windows_installer_windows.go` | `windows_installer_windows_test.go`，真实 PowerShell + 临时文件/模拟系统目标 |
| Evidence Answer | Go `agent_bff.go`、Python `evidence_answer_agent.py` | Go `agent_bff_test.go`、Python Agent 契约/API tests |
| AgentRun | Go `agent_run_bff.go`、Python `agent_run_demo_api.py` / `agent_run_runtime.py` / `agent_run_report.py` | Go `agent_run_bff_test.go`、Python runtime/report tests |
| Provider 管理 | Go `agent_provider_bff.go`、Python domain `agent_provider.py`、service `agent_provider_api.py` / `agent_provider_registry.py`、adapter `agent_provider_store.py` | Go `agent_provider_bff_test.go`、Python Provider 配置/内部 API tests |
| Lifecycle/rehydration | `internal/aiagent/`、Go `evidence_rehydration_*` / `memo_lifecycle_*`、AI lifecycle/retrieval services | 相邻 Go/Python lifecycle/rehydration tests |
| 跨语言契约 | `contracts/agent-provider-config-v1.json` 和 AgentRun/grounded-answer/lifecycle/rehydration fixtures | Go/Python/Web parity tests |

表中 Go BFF 位于 `server/router/api/v1/`，Python service 位于 `ai-service/app/services/`。
HTTP 路径与错误投影见 [API](api.md)。

## Web 功能层

`web/src/features/ai/` 拥有 `api.ts`、`hooks.ts`、`AiMemoInsights.tsx`、
`AiMemoContextPack.tsx` / `contextPack.ts`、`AiMemoEvidenceAnswer.tsx`、
`AiMemoAgentRun.tsx`、`AiMemoTemplate.tsx`、`AiMemoSummary.tsx`。
管理员表单是 `web/src/components/Settings/AgentProviderSettingsForm.tsx`，不另建客户端。

AI Inbox 是 Memo 详情页内嵌面板，不是全局 Inbox。Python/Web Context Pack 双实现使用
`contracts/context-pack-v1.json` golden 对齐；语义变化需更新 fixture，不引入第三套 builder。
`web/src/types/compat/` 只桥接依赖类型，不替换 runtime JS；移除桥接先验证 strict tsc/build。
AI 不可用时普通 Memo 编辑与搜索继续可用。

## AI Service 分层与配置

- `main.py` / `app/settings.py`：FastAPI composition、路由、启动配置。
- `app/domain/`：Agent/Provider/AgentRun、引用、生命周期、检索、Context Pack 契约。
- `app/services/`：委托、检索/回答、Provider registry、受控 runtime、报告校验与渲染。
- `app/adapters/`：SQLite、vector store、embedding 与外部实现；SDK 不进入共享 domain。
- 根 `database.py` / `llm.py` / `embedding.py` / `rag.py`：既有兼容/组合入口，不另建重复框架。
- `tests/` / `scripts/`：行为/契约/API 测试、显式诊断，不默认启动后台任务。

Agent Provider：管理员设置 → 认证 BFF → 内部 API → 加密 SQLite → 动态 registry →
Evidence Answer/AgentRun Finalizer。保存配置优先于环境回退；旧 summary/chat 不受覆盖。
master key 由部署提供，与数据库分开备份；读取仅返回掩码。Ollama 无需 API key。
Provider 20 秒，执行/连接测试 BFF 25 秒，元数据 10 秒；更短 caller deadline 优先。

## 索引与运行时边界

默认完整 Memo 使用 `memo-v1`、稳定 `memo-*` ID、deterministic embedding 和 memory store。
可选 chunk 使用 `memo-chunk-v1` 与独立 store/collection，不污染完整 Memo chat。
公共 chunk 入口默认关闭；Webhook 兼容失败保留 `code=0` / `index_status=failed`，无自动 worker。

单机 lifecycle/rehydration 已有 opt-in composition：mutation/outbox/sequence 归 Memos，
AI 只维护可重建 ledger/vector；正文读取须复核当前 authority，不回退为权限未知数据。
AgentRun 只同步运行固定 `project_summary`，无自由任务、approval、写回、共享多实例状态。
更广 lag/rebuild/reconciliation 权威运维接口是后续扩展，不从计数或异常推断它们。

## 部署与文档入口

Windows EXE 内嵌 Web/Memos **核心**，不含 Python、Qdrant、Ollama 或模型；程序和数据
分离，升级/卸载保留数据。Agent 需独立显式启动 AI 路径。默认 Compose 只启动 Memos
（0.75 CPU）和 AI Service（0.25 CPU）；Qdrant/Ollama 是 profile。Agent overlay 不向宿主
发布 AI internal port，Agent/lifecycle/自动索引默认关闭。

- 当前事实：[状态](project-status.zh-CN.md)；目标：[整体路线](roadmap.md) / [Agent 路线](agent-development-roadmap.zh-CN.md)。
- 用户入口：根双语 README / README_AI；命令：[开发](development.md) / 双语 [运维](operations.zh-CN.md)。
- 契约：[API](api.md)、[架构](architecture.md)、[Agent 设计](agent-architecture.zh-CN.md)、[决策](DECISIONS.md)。
- 包身份与验证：[v0.4.0](releases/v0.4.0.zh-CN.md)；R5/R6 审计只保留当时证明。
- 本机日志、交接、Prompt、截图不进入公共文档；新窗口只读取当前任务交接。
