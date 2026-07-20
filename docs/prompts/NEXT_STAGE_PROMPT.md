# 下一阶段 Prompt：Phase 10 gateway rollout evidence + DevMemory feedback

~~~text
Phase 10 update: the local `python -m scripts.public_chunk_gateway_contract_smoke` contract evidence is already complete. Do not repeat it as rollout proof. Choose exactly one: (A) only with a real trusted deployed gateway, Memos visibility mapping, and rollback conditions, collect deployment evidence; or (B) record one real Bug Report DevMemory feedback path. Keep `AI_PUBLIC_CHUNK_RETRIEVAL=false` unless those real gateway conditions are met.

继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，也不要并行修改 project4 下的其他 worktree。一次完成一个最小、可验证的垂直切片；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-20-devmemory-rollout-handoff.md
2. docs/PROJECT_STATUS.md 顶部
3. docs/HANDOFF.md 顶部
4. docs/roadmap.md 的 Phase 8/9/10
5. docs/DECISIONS.md 的 ADR-036/041/042/043/044
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 9a-9f 已完成 AI Inbox、Context Pack contract/UI、显式跨 Memo 选择、删除/撤销联动、Python/Web golden parity 和 SQLite 只读生命周期报告。
- 真实 Chrome/Windows 系统剪贴板验收已通过 Markdown/JSON 两种复制，且修复了复制后 React error boundary。
- Phase 8 public-chunk-v1 已实现，但 `AI_PUBLIC_CHUNK_RETRIEVAL=false` 是默认且必须保持；只有可信网关可使用 `AI_PUBLIC_CHUNK_SECRET` 对精确 raw body 签名并提供唯一 `visible_memo_ids`。
- Memos Go 仍是原始 Memo/权限事实源。AI Service 不复制用户权限系统；公共 `/api/ai/chat` 继续完整 Memo citation 语义。

本阶段唯一目标：选择下列一条路线并完成证据，不同时扩展两条。
A. Gateway rollout evidence：在受控本地/部署网关中验证 raw-body HMAC、visible scope、401/422/503、同 Memo 去重、metadata 脱敏与关闭 flag 回滚。绝不让浏览器获得 signing secret，也不以客户端声明的 Memo IDs 代替网关授权。
B. DevMemory feedback：用一个真实 Bug Report 跑 Capture -> Insight -> Review -> Context Pack，记录来源、accept/reject、删除/撤销、预算截断与复制的人工反馈；只使用安全摘要，pack 继续在内存生成。

禁止：
- 不默认开启 public chunk，不修改 `/api/ai/chat`、CitationResponse、memo-v1、chunk collection 或 Memos server/store/proto 核心。
- 不引入 Redis、Celery、Neo4j、LangChain、LlamaIndex、Prometheus、常驻 worker、外部网页、MCP 或通用聊天 UI。
- 不返回 raw content、Webhook payload、secret 或 chunk content；不删除 collection/volume。

验证：先相关定向测试；然后按改动范围运行 ai-service pytest、scripts\verify-devmemo.ps1、docker compose config --quiet、web pnpm test/tsc/build/lint；最后 git diff --check。若无真实网关或用户反馈环境，保留 contract/fake evidence，明确写为未验证，不能把离线测试写成 rollout pass。

完成后更新 PROJECT_STATUS、CHANGELOG_AI、HANDOFF、roadmap、api、structure、DECISIONS、handoff 和本 Prompt；形成独立 commit，不自动 push。
~~~
