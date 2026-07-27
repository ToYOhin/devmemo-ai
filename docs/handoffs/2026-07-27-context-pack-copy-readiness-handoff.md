# DevMemo AI Phase 11 Context Pack copy readiness 交接

更新时间：2026-07-27

## 结果

Phase 11 完成一个 Web-only 垂直切片：Context Pack 现在在复制前展示条目数、来源数与 `当前 Markdown 字符数/max_chars`；Markdown/JSON 复制都有一致的按钮成功状态和格式明确的无障碍 live-region 播报。pack 输出变化会清除上一份输出的 copied、manual fallback 与 error 状态。

该实现只消费已有浏览器内存 `context-pack-v1` 结果。没有新增 API、SQLite、Qdrant、worker、依赖、Memos 核心改动或公共 chat 行为。`AI_PUBLIC_CHUNK_RETRIEVAL=false` 保持默认关闭。

## 代码范围

- `web/src/features/ai/AiMemoContextPack.tsx`
  - 展示 items、sources、characters/max_chars。
  - JSON 与 Markdown 共用 `Copied` 反馈。
  - `role=status` + `aria-live=polite` 区分 Markdown/JSON 成功。
  - pack fingerprint 变化时清除旧复制/错误状态。
- `web/src/locales/en.json`
- `web/src/locales/zh-Hans.json`
- `web/src/locales/zh-Hant.json`
- `web/tests/ai-context-pack.test.tsx`

## 已验证

- 定向：`pnpm exec vitest run tests/ai-context-pack.test.tsx --maxWorkers=1` → `7 passed`。
- Web 全量：`pnpm exec vitest run --maxWorkers=1` → `33 files / 149 passed`。
- `pnpm build` → passed，保留既有大 chunk warning。
- `pnpm lint` → passed；其 TypeScript 步骤使用 `--skipLibCheck`。
- `git diff --check` → 在文档同步前已通过，提交前再运行。
- 独立 `pnpm exec tsc --noEmit` → 未通过，当前为 `15` 个既有第三方声明与 `src/types/view.d.ts` 错误；本切片未新增依赖或声明文件。

## 真实 Chrome 证据边界

Chrome 插件已通过 Default profile 启动并连接。Vite 最初因 Docker 后端未运行返回 `502`；随后只启动默认低 CPU Compose 服务 Memos (`0.75` CPU) 与 AI Service (`0.25` CPU)，未启动 Qdrant/Ollama，Vite 到 Memos 的通路恢复。

当前 Chrome profile 已没有有效 Memos 登录态，登录表单也没有浏览器保存的用户名/密码。验收在此停止：没有从 SQLite、local storage、token 表或历史日志提取身份，没有 seed/伪造会话，没有创建、更新、删除 Memo，也没有改变 Insight。因无法进入详情页，Phase 11 的真实摘要、复制状态重置和 Windows 系统剪贴板复核均记为未验证。

Phase 10 已完成的 Markdown/JSON Windows 系统剪贴板证据仍有效，但它发生在 Phase 11 之前，不能作为本切片运行时 pass。

## 下一步

优先从 `docs/prompts/NEXT_STAGE_PROMPT.md` 选择一个新的明确切片。若只补 Phase 11 运行时验收，前提是正常的 Memos 登录会话可用；只读复核摘要、两种复制、预算变化后的状态清除和 console error，不重跑 Capture/Review/feedback，也不从存储层绕过认证。

Route A 仍未开始。只有真实受信任 gateway、Memos 可见范围映射和关闭 flag 回滚条件齐备时，才可单独收集部署证据。保持 `AI_PUBLIC_CHUNK_RETRIEVAL=false`，不要修改 `/api/ai/chat`、CitationResponse、`memo-v1`、collection/volume 或 Memos server/store/proto。
