# R6 完成审计

R6 已合并到默认分支 `b8012ba`，且该提交的 post-merge required CI 全部通过；但 R6 仍未
release-complete：三项 canary 修复仍只存在于本地、未发布的候选分支，也没有 R6 tag 或 release artifact。
本文严格区分默认分支证据、本地候选证据与仍未关闭的授权闸门。

## 当前项目结构

- Go Memos 核心持有认证、Memo visibility、source mutation、lifecycle outbox、same-origin Agent BFF
  与 browser-safe 响应投影。
- FastAPI AI Service 持有 provider-neutral Agent contract、deterministic/可选 Provider 与 vector
  adapter、派生 SQLite/Qdrant state、durable rehydration、fixed refusal、离线 evaluation 与有界无正文
  observation。
- React Evidence Answer 只访问 Memos BFF；legacy insight/template/summary panel 仍使用可选 direct AI
  client，属于独立兼容性决策。
- 跨语言 fixture 位于 `contracts/`，公共设计与运维证据位于 `docs/`；本地 Agent 状态、Prompt、交接、
  生成结构图与浏览器产物被 Git 忽略或存放在仓库外，不属于 release artifact。

## 已验证的默认分支证据

- PR #3 已于 2026-08-09 通过 GitHub rebase 合并到 `main`，合并提交为 `b8012ba`。
- 该精确提交的 required post-merge runs 全部通过：AI Service Tests `31290057008`、Backend Tests
  `31290056997`、Frontend Tests `31290057010`、Proto Linter `31290057002`、CodeQL `31290058919`。
- strict 64-case synthetic corpus 与七项 versioned threshold 已通过 deterministic retrieval/Agent core；
  Python、Go、Web parser 对 answered、no-context 与 fixed refusal 的投影一致。
- Python engineering gate 固定了带 hash 的 Ruff 0.16.1、mypy 1.20.2 与 coverage.py 7.15.3。既有
  Windows baseline 通过 Ruff、64 个 production file 的 mypy 和 764 个测试，branch coverage 为 88.6%，
  fail-under 为 88.0%。
- 一次只使用 synthetic data 的 disposable Windows Docker/Qdrant/认证浏览器运行，证明了 same-origin
  cited answer、fixed pre-retrieval refusal、明确 disablement、AI/Qdrant 零 host port 与精确 cleanup。

## 已验证的本地候选证据

未发布的 `codex/r6-canary-demo-fixes` 候选分支包含三项窄修复：

1. `80b657b` 只投影浏览器安全的 answer、citation 与有界 trace 字段，不再透传内部响应字段。
2. `b0f76d8` 将 fixed pre-retrieval refusal 扩展到已接受的 protected-prompt 与 private-secret 同义表达。
3. `5f505b0` 使 Agent Compose overlay 中的 Memos 等待 AI Service health，同时继续保持 AI Service 与
   Qdrant 零 host-published port。

该候选在 Windows 通过 Ruff、64 个 production file 的 mypy 与 767 个测试；branch coverage 为 88.6%，
fail-under 为 88.0%。同一套低资源 canary 浏览器验收还证明了真实 BFF body 的安全投影、普通 cited answer、
原始与同义 refusal 均发生在 retrieval 前、disablement、Compose readiness、AI/Qdrant 零 host port 与精确
cleanup。这些仅是本地候选事实，不是 Linux 或 clean-checkout GitHub CI 证据。

## 仍存在的问题

- 三项 canary 修复尚未 push、review、merge 到 `main`，也没有 clean-checkout Linux CI。
- legacy insight/template/summary panel 尚未迁移到 Memos BFF，也未在 Agent-overlay 模式隐藏。
- deterministic Provider 回答适合验收但不是完善的用户级综合结果；refusal 当前仍与普通空结果共用展示。
- lifecycle outbox lag 缺 authoritative oldest-pending query；rebuild 缺跨进程 state authority；
  reconciliation 缺 dedicated owner，禁止推断这些状态。
- 多实例仍需 encrypted transport 与 shared atomic replay/capability storage。
- Docker build context 仍偏大且传输易受环境影响；readiness 已修复，但构建传输效率属于独立工作。

## 授权与下一阶段

1. 单独授权发布 `codex/r6-canary-demo-fixes`，随后在精确远端 head 上验证 required clean-checkout GitHub CI。
2. 评审后单独授权把这些修复合并到 `main`，并验证 post-merge required CI。
3. 单独授权 R6 tag、release note、image/artifact 与 release publication；CI 通过不授权 release 操作。
4. R6 release 真正收口后，先执行双语 R7-I0 definition gate，再进入代码：定义 outcome、scope、
   acceptance、rollback、隐私/数据流、审批边界、有界规划、持久运行状态、恢复与固定多工具任务集。

上述证据均不授权真实用户数据、外部 Provider、公开 AI 端口或多实例使用。
