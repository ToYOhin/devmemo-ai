# 文档更新规范

## 目的

DevMemo AI 每完成一个可验证任务切片，都必须留下可被下一次会话直接复用的项目事实、验证证据和下一步 Prompt。文档是项目状态的一部分，不是任务结束后的可选整理。

## 每个任务完成时必须更新

1. `docs/PROJECT_STATUS.md`：当前阶段、已完成内容、验证结果、阻塞项。
2. `docs/CHANGELOG_AI.md`：本次任务的用户可见变化和 commit。
3. `docs/HANDOFF.md`：下一位 Agent 的最短事实入口。
4. `docs/prompts/NEXT_STAGE_PROMPT.md`：下一步可直接执行的 Prompt。

## 按情况更新

- 架构、依赖、许可证、范围发生变化：更新 `docs/DECISIONS.md`。
- 阶段目标或优先级发生变化：更新 `docs/roadmap.md`。
- 目录、模块边界发生变化：更新 `docs/structure.md`。
- API、Webhook、数据模型发生变化：更新 `docs/api.md` 或 `docs/architecture.md`。
- 需要新窗口接续：同步更新 `docs/prompts/NEW_WINDOW_PROMPT.md`。

## 完成门禁

一个切片只有同时满足以下条件，才能标记为完成：

- 代码或文档改动范围明确，没有混入无关重构。
- 相关测试、构建、手动烟测或阻塞证据已记录。
- 变更已形成独立 commit。
- `PROJECT_STATUS`、`CHANGELOG_AI`、`HANDOFF`、`NEXT_STAGE_PROMPT` 已同步。
- 下一步 Prompt 写明目标、范围、不要做什么、验证命令和停止条件。
- 未验证的内容必须明确写成“未验证/阻塞”，不能写成完成。

## 推荐更新顺序

```text
实现 -> 测试 -> 验证 -> commit -> PROJECT_STATUS -> CHANGELOG_AI
      -> DECISIONS/ROADMAP/STRUCTURE/API（按需）
      -> HANDOFF -> NEXT_STAGE_PROMPT -> git diff --check -> commit
```

## 文档写作规则

- 事实优先：写路径、命令、commit、测试结果和阻塞原因。
- Prompt 保持短而可执行，详细背景放在引用的文档中。
- 不写 API key、密码、个人隐私或本机临时 token。
- 公共 README 不放本机绝对路径；仓库内部交接文档可以使用工作区路径。
