# R6 完成审计

R6 已在本地实现 sanitized evaluation、fixed refusal 与 content-free observability 切片，但尚未达到 release-complete。
本记录严格区分当前证据，以及仍需外部工具、runtime 授权、CI publication 或 release authority 的闸门。

## 当前项目结构

- Go Memos 核心持有认证、Memo visibility、source mutation、lifecycle outbox、same-origin Agent BFF 与安全响应投影。
- FastAPI AI Service 持有 provider-neutral Agent contract、deterministic/可选 Provider 与 vector adapter、派生
  SQLite/Qdrant state、durable rehydration、fixed refusal、离线 evaluation 与有界进程内 observation。
- React Web 的 Evidence Answer 只访问 Memos BFF；legacy insight/template/summary panel 仍使用可选 direct AI client，
  属于独立兼容性决策。
- 跨语言 fixture 位于 `contracts/`，公共设计与运维证据位于 `docs/`；本地 Agent 状态、Prompt、交接与生成结构图被
  Git 忽略，不属于 release artifact。

## 本地已验证

- strict 64-case synthetic corpus 与七项 versioned threshold 已实际运行 deterministic in-memory retrieval/Agent core；
  fixed pre-retrieval refusal 接线后，全部 case 与 threshold 通过。
- Python、Go、Web exact parser 对 answered、no-context、fixed refusal 投影一致；未知或混合 trace shape fail closed。
- AI answer、retrieval、configured Provider 的固定 outcome/latency sample 只在既有 Agent ownership 下产生；Go lifecycle
  outcome/retry/quarantine 只来自已持久 outbox transition。
- 本次切片的 focused Python/Go/Web、TypeScript、format、content leak、credential 与 local-path 检查通过。

## 尚未完成

1. **Python engineering gate：** repo 与当前环境只有 pytest，没有 ruff、mypy、coverage 或等价缓存工具；AI workflow
   也只运行 tests。仍需选择并固定 dev tool、安装依赖、建立 baseline config，并在本地验证 CI command。
2. **Clean-checkout CI：** R6 commits 仍在本地，GitHub workflow 尚未运行，不能声称当前 Linux unit/integration/security/
   build 可复现。
3. **R6 disposable browser proof：** R5 已证明 lifecycle/browser product path，但新增 refusal terminal、Go safe projection
   与 Web render 目前只有 unit/TestClient 证据。仍需 disposable 认证浏览器验证 refusal、普通 cited answer、disablement 与
   exact cleanup。
4. **Release gate：** 尚无 reviewed default-branch merge、R6 tag、release note、image 或 release artifact；README 不得声称
   R6 已发布。

## 授权顺序

1. 授权通过网络安装并 lock/update 选定 Python lint/type/coverage 工具；
2. 授权 disposable Docker/Qdrant/temp account/Memo/volume/secret 与认证浏览器验收 R6 delta；
3. 授权 push feature branch 并验证 required CI；
4. review 后再单独授权 merge/default-branch publication、tag 与 release。

上述 R6 闸门关闭前，不虚构或实现 R7。R6 收口后，应先在双语 roadmap 定义 R7 outcome、scope、acceptance、
rollback、隐私/数据流影响与授权闸门，再进入代码切片。

outbox lag 仍缺权威 oldest-pending query；rebuild observability 仍缺已评审跨进程 state authority；reconciliation 在拥有
dedicated owner 前继续阻断。不得推断这些 metric 来制造 R6 已完成的表象。
