# Phase 10 Context Pack 浏览器恢复证据

更新时间：2026-07-20

## 已验证

- 本机 Compose 与 Vite 代理健康；Memos 未认证端点返回预期 `401`，AI Service 为 deterministic `ok`。
- Vite 重启后，接管长期 Chrome 用户标签可能超时。使用同一 Chrome profile 的新标签可正常加载既有测试 Memo，不需要重新登录、创建 Memo 或修改状态。
- 新标签可见既有 accepted Insight、显式来源选择和 Context Pack。将 `max_chars` 设置为 `64` 后，UI 显示 `max_chars` 截断提示，预览受该预算约束。
- 真实 Chrome 的坐标鼠标操作分别点击 `Copy Markdown` 与 `Copy JSON` 后，host Windows `Get-Clipboard` 读取到新的安全 Context Pack 输出。Markdown 长度为 `530` 且具有预期标题；JSON 长度为 `1,754`、可解析且 `pack_version=context-pack-v1`。两次输出均未匹配 raw Webhook payload 或 secret 标记。
- 页面在两次复制后没有 console error 或 React error boundary。

## 证据边界

- 早先 Playwright 式自动化点击没有改写 host clipboard；该结果是自动化桥接路径限制，不是产品失败或本次复制通过的证据。上述结论只基于真实 Chrome UI 的指针点击和随后 host Windows 系统剪贴板复核。
- 没有新增人类主观反馈答案、没有 delete/revoke、没有新 Memo、没有新的 Insight 状态变更。

## 后续

真实参与者现在只需回答四项简短反馈：来源是否易懂、accepted Review 是否可信、64 字符预算是否有用、复制行为是否符合预期。不要重复已完成的 Capture/Review，也不要为了收集证据删除或撤销。
