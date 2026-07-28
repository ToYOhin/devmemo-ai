# Phase 10 route B 本地 Webhook → Insight → Review 证据

更新时间：2026-07-20

## 范围与边界

- 仅使用 `H:\DevMemoAI` 主工作树、默认低 CPU Compose 路径和一个既有非敏感测试 Bug Report。
- 允许的变更是当前认证 Memos 用户的一个本地 AI Service webhook，以及该既有 Memo 的普通 UI 更新；没有创建第二条 Memo，没有删除数据。
- Memos 仍是原始 Memo 和权限事实源；AI Service 只保存派生 SQLite 状态。`AI_PUBLIC_CHUNK_RETRIEVAL=false`、公共 `/api/ai/chat`、`memo-v1`、chunk collection 与 volume 均未改变。

## 已验证事实

1. Compose Memos 以 `--allow-private-webhooks` 运行，使当前用户可将既有 Webhook 指向 Docker 私网内的 AI Service。该开关仅为本机受控开发拓扑服务；浏览器没有获得 AI secret，也没有提供或签署 Memo 可见范围。
2. 当前认证用户已配置一个 AI Service webhook。对既有测试 Bug Report 的普通认证 UI 更新触发真实事件；AI Service 记录为已处理。
3. Memos webhook 使用 `memos/<uid>` 资源名，而详情页查询使用终端 UID。AI Service 现规范化这一映射；回归测试覆盖终端 UID 读取派生 Insight，避免同一 Memo 形成两份状态。
4. 该事件产生一个持久化 pending Insight，随后使用已授权的一次状态变更更新为 `accepted`，版本递增至 `2`。此处不记录 Insight ID、Memo ID、标题、摘要、原文或 Webhook payload。
5. 运行中 Compose 的只读 aggregate 通过 `docker compose exec -T ai-service python -m scripts.devmemory_lifecycle_report` 执行，显示十条 AI 派生 Insight、状态分布为 accepted `5`/pending `4`/rejected `1`，以及八条 processed webhook events。该输出只包含安全计数。

## 诊断更正

此前在宿主机直接运行 lifecycle CLI，默认 SQLite 路径不对应 Docker Compose 的 AI Service 挂载卷，因而读到空/不同的状态并错误写成 `memo_insights=0` blocker。该结果不能作为容器服务的运行态或产品阻塞证据。今后 Compose 场景必须使用容器内 CLI，或者显式指定确实可访问的数据库路径。

## 未验证，不得升级为通过

- 本轮未重新观察稳定认证浏览器中的 Context Pack 预算截断、Markdown/JSON 系统剪贴板写入或页面无 error boundary；Vite 重启后浏览器控制不可用。
- 未执行 delete/revoke，也不应为了补证据执行它们。
- 未采集四项真实参与者的主观反馈答案。
- 这不是受信任 gateway 的部署/灰度/回滚证据，绝不因此开启 public chunk。

## 后续

仅在稳定认证浏览器与真实参与者同时具备时，复用现有测试 Memo 完成安全 Context Pack、最小预算、两种复制结果和四项简短反馈。否则记录不可用原因并停止；不得创建第二条 Memo、seed SQLite、绕过 Memos 认证或伪造反馈。

## 验证

- 新增 resource-name 规范化回归：`1 passed`。
- AI Service 全量：`188 passed`，保留一条既有 Starlette/httpx 弃用警告。
- `scripts/verify-devmemo.ps1`：`188 passed`；`docker compose config --quiet`：通过。
- 低 CPU 串行 Web：Context Pack 定向 `13 passed`；全量 `33 files / 149 passed`；build 与项目 `pnpm lint` 通过。
- 重新启动的本地 Vite 代理返回 Memos 未认证 `401`（而非旧目标的 `502`）；AI Service health 为 deterministic `ok`。
- 独立 `pnpm exec tsc --noEmit` 仍由 13 条既有第三方声明与 `src/types/view.d.ts` strict errors 阻塞；项目 lint 使用 `--skipLibCheck` 并已通过。
