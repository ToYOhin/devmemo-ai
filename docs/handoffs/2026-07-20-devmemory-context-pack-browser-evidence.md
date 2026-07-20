# Phase 10 Context Pack 浏览器恢复证据

更新时间：2026-07-20

## 已验证

- 本机 Compose 与 Vite 代理健康；Memos 未认证端点返回预期 `401`，AI Service 为 deterministic `ok`。
- Vite 重启后，接管长期 Chrome 用户标签可能超时。使用同一 Chrome profile 的新标签可正常加载既有测试 Memo，不需要重新登录、创建 Memo 或修改状态。
- 新标签可见既有 accepted Insight、显式来源选择和 Context Pack。将 `max_chars` 设置为 `64` 后，UI 显示 `max_chars` 截断提示，预览受该预算约束。
- Markdown 与 JSON 复制按钮均由 UI 调用；页面未报告 console error 或 React error boundary。

## 未验证

- 自动化表面没有更新 Windows 系统剪贴板：两次按钮调用后 host clipboard 仍为非 Context Pack 内容。因此本记录不声称新的 Markdown/JSON 系统复制通过，也不把它判为产品回归。
- 没有新增人类主观反馈答案、没有 delete/revoke、没有新 Memo、没有新的 Insight 状态变更。

## 后续

真实参与者在稳定 Chrome 会话中只需回答四项简短反馈：来源是否易懂、accepted Review 是否可信、64 字符预算是否有用、复制行为是否符合预期。不要重复已完成的 Capture/Review，也不要为了收集证据删除或撤销。
