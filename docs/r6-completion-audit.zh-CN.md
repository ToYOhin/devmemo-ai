# R6 完成审计

R6 已完成发布。PR #6 将 canary 验收修复合并到 `main`；PR #7 完成 release metadata；
annotated tag `v0.2.0` 精确解析到默认分支提交
`eddaa602537cda1adc27c0cd1d8c58b40c8e503b`。本文继续把 release、clean-checkout CI、
本地 Windows 验证与 synthetic canary 作为相互独立的证据通道。

## 当前项目结构

- Go Memos 核心持有认证、Memo visibility、source mutation、lifecycle outbox、same-origin
  Agent BFF、current-authority rehydration 与 browser-safe 响应投影。
- FastAPI AI Service 持有 provider-neutral Agent contract、deterministic/可选 Provider 与
  vector adapter、派生 SQLite/Qdrant state、fixed refusal、离线 evaluation 与有界无正文 observation。
- React Evidence Answer 只访问 Memos BFF；legacy insight/template/summary panel 仍使用可选
  direct AI client，属于独立的产品加固决策。
- 跨语言 fixture 位于 `contracts/`，公共设计与运维证据位于 `docs/`；本地协作状态、交接、
  生成结构图与浏览器产物被 Git 忽略或存放在仓库外，不属于 release artifact。

## 已验证的发布证据

- PR #6 精确 head `bc84b244ec6cbd3186471c08fa4b0c05e832db6f` 的 clean-checkout
  AI Service Tests `31310964079`、Backend Tests `31310964022`、Frontend Tests
  `31310964015`、Proto Linter `31310964026` 与 required CodeQL checks 全部通过。
- PR #6 合并到 `main` 为 `0f6a1ecf32068a3ef3a429c25d6c0e7c7b5eff41`；该精确提交的
  post-merge AI Service、Backend、Frontend、Proto 与 CodeQL contexts 全部通过。
- PR #7 精确 head `a60932a6226bc17a77cd410138a2c481ad2ab900` 合并到 `main` 为
  `eddaa602537cda1adc27c0cd1d8c58b40c8e503b`。
- annotated tag `v0.2.0` peel 到 `eddaa602`；Release run `31357981476` 成功；已发布
  GitHub Release 包含 checksums 与 Windows、Linux、macOS 压缩包。
- strict 64-case synthetic corpus 与七项 versioned threshold 已通过 deterministic
  retrieval/Agent core；Python、Go、Web parser 对 answered、no-context 与 fixed-refusal 投影一致。
- release candidate 通过 Ruff、64 个 production file 的 mypy 与 767 个 Windows 测试；
  branch coverage 为 88.6%，fail-under 为 88.0%。

## Synthetic canary 边界

一次只使用 synthetic data 的 disposable Windows Docker/Qdrant/认证浏览器 canary，证明了
same-origin cited answer、原始与同义 pre-retrieval refusal、browser-safe BFF projection、明确
disablement、按 health 排序的 Compose startup、AI/Qdrant 零 host port 与精确 cleanup。
这些仍是发布前 synthetic 验收证据，不是真实用户数据、外部 Provider 结果、published-image 证明或
发布后浏览器运行。

## 仍存在的问题

- legacy insight/template/summary panel 尚未迁移到 Memos BFF，也未在 Agent-overlay 模式隐藏。
- deterministic Provider 回答适合验收但不是完善的用户级综合结果；refusal 仍与普通空结果共用展示。
- lifecycle outbox lag 缺 authoritative oldest-pending query；rebuild 缺跨进程 state authority；
  reconciliation 缺 dedicated owner，禁止推断这些状态。
- 多实例仍需 encrypted transport 与 shared atomic replay/capability storage。
- Docker build context 仍偏大且传输易受环境影响；readiness 已修复，构建传输效率属于独立工作。

## 下一阶段

R6 publication 已关闭。进入任何 R7 实现前，先完成双语 R7-I0 definition gate，明确 outcome、scope、
non-goals、threat model、acceptance、rollback、隐私/数据流、审批边界、有界规划、持久运行状态、恢复与
固定多工具任务集。

legacy direct-AI panel compatibility 仍是独立 product-hardening slice：要么在 Agent-overlay 模式隐藏
不支持的 panel，要么把读取与审核写操作迁移到认证 Memos BFF，并使用严格安全投影。不得通过发布
AI Service host port 修复兼容性。

R6 证据不授权真实用户数据、外部 Provider、公开 AI 端口、自治后台任务或多实例使用。
