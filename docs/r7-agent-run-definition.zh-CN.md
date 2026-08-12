# R7-I0 AgentRun 定义门禁

状态：R7-I0 definition gate 已合并到
`origin/main@3dbddc3a6e8c17aeb90d35100137e436f2b7a4f7`，仅包含定义。本文不新增 AgentRun
runtime、route、database、migration、worker 或 feature default，并细化
[Agent 开发路线图](agent-development-roadmap.zh-CN.md)中的下一门禁。

## 结果

定义一套 provider-neutral、有边界、可恢复的 AgentRun contract：保留 Memos 的认证与 visibility
authority，产出带证据引用的 report artifact，并在证据或 authority 变化时 fail closed。

R7-I0 的完成标准是中英文对模型、状态机、budget、ownership、recovery、approval boundary、脱敏
timeline、acceptance fixture 与 rollback 作出无歧义定义。本阶段不包含可执行实现。

## 范围

- 定义 `AgentRun`、`AgentStep`、`RunEvent`、`ApprovalRequest` 与 `Artifact`。
- 定义合法 run transition 与 terminal 行为。
- 固定首阶段工具集为 `search_memos`、`get_memo_evidence` 与 `create_report_artifact`。
- 定义有界执行、idempotency、checkpoint、retry、resume、cancel 与 process restart 语义。
- 定义 source revision、visibility、approval、privacy 与 audit 行为。
- 为后续 contract 切片定义 deterministic acceptance fixture。

## 非目标

R7-I0 不实现 Python、Go、TypeScript、Proto、migration、Compose、环境变量、runtime wiring、
background job、model routing、Memo write、external write tool 或浏览器体验。它不改变 default、认证、
visibility、存储、端口或当前 R6 行为。

它不主张真实 Provider、真实用户数据、浏览器自动化、多实例或生产就绪。

## 威胁模型与不变量

本设计假定可能出现恶意 Memo 文本、prompt injection、伪造或重放 run request、过期 source revision、
run 期间 visibility 变化、重复投递、进程中断、过期或重复 approval、虚构 citation 的 Provider output，
以及提取 protected prompt、secret、capability、embedding 或其他用户内容的尝试。

以下不变量必须成立：

1. Memos 在检索前认证用户并计算 visibility。
2. 每次 evidence read 都根据 Memos 当前 authority 重新授权。
3. run 不得扩大初始 user、workspace 或 source scope。
4. answer 或 artifact 只能使用 server 验证过的 evidence reference。
5. evidence 缺失、authority 过期或副作用不明确时 fail closed。
6. planning 与 tool execution 必须有界，禁止递归或 unbounded planning。
7. terminal run 不可变，只允许追加脱敏 audit metadata。

## 所有权与数据流

1. 浏览器向 same-origin Memos BFF 提交已认证任务，并且只接收 browser-safe 的 run、timeline、
   approval 与 artifact projection。
2. Memos 持有 identity、visibility、source Memo mutation、source revision、lifecycle outbox state、
   current-authority check 与 capability issuance。
3. Memos BFF 固定授权 scope，只把有界且 content-minimized 的 scope 委派给 AI Service；浏览器永不
   直接调用 AI Service。
4. AI Service 持有 orchestration、provider-neutral run/step state、派生 retrieval index、checkpoint、
   脱敏 event 与生成的 artifact bytes。它们都是派生状态，必须能在不修改 source Memo 的前提下重建或删除。
5. `Artifact` 是派生输出，绝不是 source authority。Memos 在投影 artifact metadata 或签发有界下载前，
   重新检查请求者 visibility；artifact 不得恢复对已不可见证据的访问。

## Provider-neutral 数据模型

identifier 是 server 生成的不透明值，timestamp 使用 UTC。枚举类型与 reason code 是带版本 contract，
不是 Provider 专用字符串。

### AgentRun

| 字段 | Contract |
| --- | --- |
| `run_id` | 稳定的不透明 identifier |
| `subject_id` | 已认证 Memos principal；浏览器不得指定 |
| `scope_ref` | Memos 签发的有界 source scope reference |
| `request_key` | 绑定 subject 与 operation 的 idempotency key |
| `status` | 下文六种状态之一 |
| `budget` | 已接受且不可变的 step、call 与 active-time ceiling |
| `source_snapshot` | 不含正文的 authority version/revision set |
| `created_at`, `updated_at` | UTC lifecycle timestamp |
| `terminal_reason` | terminal run 的固定安全 code，否则不存在 |
| `last_event_seq` | 已提交 timeline 的单调 sequence |

### AgentStep

| 字段 | Contract |
| --- | --- |
| `step_id`, `run_id`, `ordinal` | 稳定 identity 与 run 内全序 |
| `kind` | `plan`、`tool`、`approval` 或 `finalize` |
| `status` | `queued`、`running`、`succeeded`、`failed` 或 `cancelled` |
| `tool_name` | tool step 使用固定工具名，其他 step 不存在 |
| `attempt` | 从零开始且有界的 attempt number |
| `input_digest` | normalized safe input 的 digest，绝不保存 raw content |
| `checkpoint_ref` | 最近一次原子提交的 step checkpoint |
| `started_at`, `finished_at` | 适用时记录 UTC 时间 |
| `outcome_code` | 固定且不含正文的 outcome code |

### RunEvent

| 字段 | Contract |
| --- | --- |
| `event_id`, `run_id`, `seq` | 稳定 identity 与 run 内单调顺序 |
| `event_type`, `schema_version` | 固定 event contract 与版本 |
| `step_id` | 适用时关联 step |
| `safe_details` | 仅允许 allowlist 中不含正文的 metadata |
| `occurred_at` | server timestamp |
| `prev_digest`, `event_digest` | 可选 tamper-evident 排序字段 |

### ApprovalRequest

| 字段 | Contract |
| --- | --- |
| `approval_id`, `run_id`, `step_id` | 稳定 approval identity |
| `action_type` | 带版本 action class，绝不是任意可执行文本 |
| `action_digest` | 绑定精确 proposed action 与 argument 的 digest |
| `source_snapshot` | proposal 所依据的 authority revision |
| `requested_at`, `expires_at` | 显式有界 approval window，不设隐式 default |
| `status` | `pending`、`approved`、`rejected`、`expired` 或 `superseded` |
| `decided_by`, `decided_at` | 已认证 decision audit 字段 |

### Artifact

| 字段 | Contract |
| --- | --- |
| `artifact_id`, `run_id`, `step_id` | 稳定派生输出 identity |
| `kind`, `media_type`, `schema_version` | allowlisted format contract |
| `storage_ref` | 仅 server 可见的 derived-object reference |
| `digest`, `size_bytes` | integrity 与 size metadata |
| `evidence_refs` | 用于派生 artifact 的已授权 Memo UID/revision reference |
| `created_at`, `expires_at` | lifecycle 与 retention boundary |
| `status` | `available`、`revoked` 或 `expired` |

## Run 状态机

run 只有 `queued`、`running`、`waiting_approval`、`succeeded`、`failed` 与 `cancelled` 六种状态。

| 起点 | 合法转换 | 触发条件 |
| --- | --- | --- |
| `queued` | `running` | worker 使用已提交 budget claim run |
| `queued` | `cancelled` | 执行前收到已授权 cancel |
| `running` | `waiting_approval` | 未来 approval-gated action 已完整绑定并 checkpoint |
| `running` | `succeeded` | final output 验证并提交 |
| `running` | `failed` | 固定 terminal failure 或 budget 耗尽 |
| `running` | `cancelled` | 在安全边界观察到已授权 cancel |
| `waiting_approval` | `running` | 原子消费一条有效、未过期且 authority 当前的 approval |
| `waiting_approval` | `failed` | rejection、expiry、stale authority 或无效 approval |
| `waiting_approval` | `cancelled` | 观察到已授权 cancel |

`succeeded`、`failed` 与 `cancelled` 是 terminal 状态。任何 transition 都不能重新打开 terminal run。
process restart 是持久状态内的 recovery，不是新状态或隐式 transition。

## 固定首阶段工具

- `search_memos`：在 delegated scope 内返回不含正文的 ranked candidate；不得接受浏览器指定的 identity
  或扩大的 scope。
- `get_memo_evidence`：重新检查当前 authority，只返回当前 step 所需且绑定精确 revision 的 evidence。
- `create_report_artifact`：从验证过的 evidence reference 幂等创建派生 report；不创建或修改 Memo。

首阶段不允许其他工具。所有未来 Memo write tool 必须保持 approval-gated，并另行完成 threat-model、
schema、runtime 与产品评审。R7-I0 不定义 write tool，也不授权 source data 副作用。

## 执行预算

首版 contract ceiling 对每个已接受 run 均不可变，并不改变当前 runtime default：

- 最多 12 个 step，包括 planning 与 finalization；
- 总计最多 8 次 tool call，每个 tool step 最多重试 1 次；
- active execution 最多 120 秒，不计入 `waiting_approval`；
- 单次 tool attempt 最多 30 秒；
- 最多 3 个 artifact，每个最多 1 MiB。

达到任一 ceiling 时生成固定、不含正文的 failure code。run 不得自行扩大 budget、通过创建另一 run 规避
ceiling，也不得在剩余 budget 已无法完成合法 next step 时继续 planning。

## Idempotency、checkpoint、retry、resume、cancel 与 restart

- Memos 按 `(subject_id, request_key)` 对创建请求去重；相同请求返回既有 run，digest 冲突则 fail closed。
- 每次 tool attempt 使用由 run、step、attempt、tool 与 normalized safe-input digest 派生的稳定 key；
  `create_report_artifact` 对同一 key 返回同一 artifact。
- 每个 checkpoint 原子提交 run state、step outcome、artifact metadata 与对应 event；不得投影 partial result。
- 只有 classified transient failure 才能在一次 retry ceiling 内重试；重试前必须重新检查 cancel、source
  revision 与 visibility。
- resume 从最后一次已提交 checkpoint 开始；不信任未提交的 Provider/tool output，也不重复未知副作用。
- cancel 必须认证且幂等。worker 在 planning 前、每次 tool call 前后、artifact commit 前与 finalization 前检查。
- process restart 后，`queued` run 可被 claim；`running` run 从最后 checkpoint 恢复；
  `waiting_approval` run 保持暂停，直到有效 decision 或 expiry；terminal run 保持 terminal。

## 完整且脱敏的 Timeline

每次 state transition、step start/end、tool attempt、retry、approval decision、checkpoint、artifact lifecycle
change、cancel 与 terminal outcome 都产生一个有序 `RunEvent`。safe details 可以包含 ID、固定 reason code、
tool name、count、duration、source UID/revision reference、digest 与 artifact metadata。

timeline 绝不能记录 raw prompt、raw Memo content、secret、token、internal capability、embedding、Provider
hidden reasoning 或不受限的 tool argument/result。browser projection 使用比 server audit storage 更严格的
allowlist；错误文本映射为固定 safe code。

## Approval 与 Authority 失败

- approval 绑定一个 subject、run、step、action digest 与 source snapshot，不能批准已修改 action。
- `expires_at` 之后收到的 approval 标记为 `expired`，run fail closed；request 创建时必须明确 expiry。
- 第一条有效 approval decision 被原子消费。重复相同 delivery 保持幂等；冲突或已消费 decision 被拒绝并
  记录，且不得再次执行 action。
- stale source revision 使 pending action 失效并 fail closed。
- visibility change 触发 current-authority recheck，撤销不可访问的 evidence/artifact projection，并使 active
  step 失败；cached access 永远不能覆盖 Memos authority。

## Acceptance Fixtures

后续 contract 切片必须增加以下最小集合的脱敏 deterministic fixture。每个 fixture 定义 input、有序 safe
event、terminal state、tool-call count、evidence revision 与 artifact/approval outcome。

| Fixture | 必须得到的结果 |
| --- | --- |
| `readonly_multistep_success` | search、evidence read 与 report creation 成功，并带有效 citation |
| `no_evidence_termination` | 不进行 Provider synthesis、不创建 artifact，以固定 no-evidence result 终止 |
| `safe_refusal` | protected-prompt 或 secret 请求在 retrieval 前拒答 |
| `stale_revision` | revision mismatch 在使用 evidence 或提交 artifact 前 fail closed |
| `visibility_change` | run 中途失去访问权后撤销 projection 并安全终止 |
| `waiting_approval_resume` | contract-level 未来 action 暂停、消费一次有效 approval 后恢复，但不实现 write tool |
| `duplicate_retry` | duplicate request/tool delivery 保持幂等且不超过 budget |
| `cancel` | 已授权 cancel 到达 `cancelled`，此后不再提交 tool 或 artifact |
| `restart_recovery` | restart 精确从最后 checkpoint 恢复，不产生重复副作用 |

## 回滚

R7 默认关闭。R7-I0 不新增 route、runtime selection、worker、database migration、环境变量或 source-data
mutation。回滚只需删除双语定义和任何后续 definition-only fixture asset，再移除 roadmap 链接。既有 R6
行为与数据不变。

## 未验证且需单独授权的范围

本定义不验证或授权真实 Provider、真实用户数据、浏览器自动化、background autonomous job、多实例或
external write tool。任何相应主张前，都必须另行设计并验收 encrypted transport、shared atomic
replay/capability storage、production retention 与 operational ownership。
