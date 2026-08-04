# R6 完成审计

R6 已实现 sanitized evaluation、fixed refusal 与 content-free observability 切片，并已在 feature branch 发布且具备
clean-checkout CI 证据，但尚未达到 release-complete。本记录严格区分当前证据与仍需 release authority 的闸门。

## 当前项目结构

- Go Memos 核心持有认证、Memo visibility、source mutation、lifecycle outbox、same-origin Agent BFF 与安全响应投影。
- FastAPI AI Service 持有 provider-neutral Agent contract、deterministic/可选 Provider 与 vector adapter、派生
  SQLite/Qdrant state、durable rehydration、fixed refusal、离线 evaluation 与有界进程内 observation。
- React Web 的 Evidence Answer 只访问 Memos BFF；legacy insight/template/summary panel 仍使用可选 direct AI client，
  属于独立兼容性决策。
- 跨语言 fixture 位于 `contracts/`，公共设计与运维证据位于 `docs/`；本地 Agent 状态、Prompt、交接与生成结构图被
  Git 忽略，不属于 release artifact。

## 已验证证据

- strict 64-case synthetic corpus 与七项 versioned threshold 已实际运行 deterministic in-memory retrieval/Agent core；
  fixed pre-retrieval refusal 接线后，全部 case 与 threshold 通过。
- Python、Go、Web exact parser 对 answered、no-context、fixed refusal 投影一致；未知或混合 trace shape fail closed。
- AI answer、retrieval、configured Provider 的固定 outcome/latency sample 只在既有 Agent ownership 下产生；Go lifecycle
  outcome/retry/quarantine 只来自已持久 outbox transition。
- 本次切片的 focused Python/Go/Web、TypeScript、format、content leak、credential 与 local-path 检查通过。
- Python engineering gate 已固定 hash-locked Ruff 0.16.1、mypy 1.20.2 与 coverage.py 7.15.3。Windows 本地
  Ruff 对明确 AI source/test 范围通过，mypy 对 64 个 production source file 通过，764 个测试全部通过，branch
  coverage 为 88.6%，初始 fail-under 为 88.0%。
- 当前 checkout 已完成一次 disposable Windows Docker/Qdrant/headed-browser 验收，仅使用一个 synthetic account、
  一个 synthetic Memo 与 deterministic Provider。真实认证、same-origin 链路证明了普通 cited answer、零 citation 的固定
  pre-retrieval refusal、明确 disabled-state UI、AI/Qdrant 零 host port，以及 container、network、volume、验收 image、
  browser state、临时 build context、credential、data 与 Memos host listener 的精确清理。accepted run 前已关闭 Qdrant
  telemetry。同一浏览器运行也再次确认：port 8000 按设计不发布时，legacy direct-AI panels 仍然失败。
- Draft PR #3 在 feature-branch head `30a275d` 上通过 clean-checkout GitHub CI：AI Service Tests run
  `30908048004`、Backend Tests run `30908048498`、Frontend Tests run `30908047993`、Proto Linter run
  `30908048511` 与 CodeQL run `30908042878`。这是 feature branch/PR 证据，不是 default-branch release 证据。

## 尚未完成

1. **Release gate：** 尚无 reviewed default-branch merge、R6 tag、release note、image 或 release artifact；README 不得声称
   R6 已发布。

## 授权顺序

review 后仍需单独授权 merge/default-branch publication、tag 与 release。PR CI 通过不授权其中任何操作。

上述 R6 闸门关闭前，不虚构或实现 R7。R6 收口后，应先在双语 roadmap 定义 R7 outcome、scope、acceptance、
rollback、隐私/数据流影响与授权闸门，再进入代码切片。

outbox lag 仍缺权威 oldest-pending query；rebuild observability 仍缺已评审跨进程 state authority；reconciliation 在拥有
dedicated owner 前继续阻断。不得推断这些 metric 来制造 R6 已完成的表象。
