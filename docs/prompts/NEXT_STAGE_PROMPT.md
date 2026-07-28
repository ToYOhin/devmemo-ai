# 下一阶段 Prompt：项目完成态与下一切片选择

~~~text
Phase 13 and the 2026-07-28 open-source release slices are complete. DevMemo AI has a non-official downstream identity, upstream/MIT notice, community and security files, a safe default Compose path, and DevMemo-owned CI/release/image namespaces. The migration fixture and golangci timeout fixes have passed real PR CI; the GHCR canary and private `v0.1.0-rc.1` prerelease both passed, including runner-side image inspection and six Release assets. The Windows archive checksum, extraction, and `--help` were verified locally at low CPU. Public stable release is still NO-GO: the repository is private, has zero Actions secrets (`RELEASE_PLEASE_TOKEN` is absent), and has no verified public private-vulnerability-reporting channel. Read `docs/handoffs/2026-07-28-rc-release-validation-handoff.md` and `docs/release-preflight.md`. Keep `AI_PUBLIC_CHUNK_RETRIEVAL=false`.

继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，也不要并行修改 project4 下的其他 worktree。只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-28-rc-release-validation-handoff.md
2. docs/PROJECT_STATUS.md 顶部
3. docs/HANDOFF.md 顶部
4. docs/roadmap.md 的发布/后续选择
5. docs/DECISIONS.md 的 ADR-051 至 ADR-054
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前完成态：
- 当前已定义的内部工程路线与本地发布准备切片已完成；没有默认的新实现任务。
- Phase 10 route B 已完成，不重复。Phase 11 真实详情页/系统剪贴板复核因当前 Chrome profile 无有效 Memos 登录态而未验证，不能写成 pass。
- route A 仍缺少真实受信任 gateway、Memos 可见范围映射和 rollback 条件；保持 `AI_PUBLIC_CHUNK_RETRIEVAL=false`，不扩展浏览器签名。
- 默认保持 deterministic + memory、`AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、`AI_VECTOR_STORE=memory`。

在用户明确选择前：只回答、诊断或准备无副作用的提案；不得自行实现新功能、修改 API/数据库/依赖、启动外部 profile、创建或修改 Memo/Insight、提取 token、绕过认证，或把历史证据冒充为新验收。也不得重新把私网 Webhook 放行写入默认 Compose、复用上游发布命名空间，或跳过既有 CI/发布前置条件。未经明确授权，不得 push、改仓库可见性、设置长期 PAT secret、打 tag 或发版。

可选的下一切片（必须由用户选择）：
1. 有正常 Memos 登录会话时，对 Phase 11 做只读 UI/系统剪贴板复核。
2. 有真实 gateway、visibility mapping 与 rollback 条件时，评估 route A 的独立受控 rollout。
3. 选择一个新的受控产品功能目标并先写最小 proposal/验收边界。
4. 选择发布准备收尾：由维护者先完成 `docs/release-preflight.md` 的外部仓库设置；随后单独授权公开可见性、稳定 tag 或正式发布。不得把现有私有 RC 当作正式发布。
~~~
