# DevMemo AI 变更记录

## 2026-07-12

### Phase 2b：结构化模板持久化

- 新增 `memo_templates` SQLite 表，保存 `memo_id/kind/payload/raw_content/created_at/updated_at`。
- Memos Webhook 对 Code Snippet/Bug Report 做幂等 upsert，普通 Memo 不写模板表。
- 新增 `GET /api/ai/templates/{memo_id}`，缺失返回 404。
- 验证：AI Service `15 passed`，`scripts/verify-devmemo.ps1` 通过。
- Commits：`fb69eca`、`7d3007b`。

### Phase 2：模板解析切片

- 新增 provider-neutral 的 `CodeSnippet`、`BugReport`、`ParsedMemo` 模型。
- 支持 frontmatter、`type=code/bug`、代码 fence、Bug Report headings 和内联字段。
- Memos Webhook 返回 `memo_type`、结构化 `template`，空内容安全忽略。
- 验证：AI Service `10 passed`，`scripts/verify-devmemo.ps1` 输出 `DEVMEMO_VERIFY_OK`。
- Commits：`d6578d0`、`987a95f`、`dffcdf2`。

### 文档与交接规范

- 新增任务完成后的 Markdown 更新门禁。
- 新增项目状态、变更记录、决策、handoff 和下一步 Prompt 文件。
- 新增 Windows 验证脚本和 Phase 2 接续 Prompt。
- 验证：`scripts/verify-devmemo.ps1` 输出 `DEVMEMO_VERIFY_OK`。
- Commit：`12bf84c docs: add task handoff and prompt workflow`。

### 开发基础与路线

- Go 1.26.2 安装到 `G:\Go`。
- Go 缓存和工作区迁移到 `G:\GoWorkspace`。
- 明确 Memos upstream 区与 AI Service 适配器区的边界。
- 记录 Qdrant、FastEmbed、qdrant-client、Ollama 的采用策略。
- 完整 Go 测试仍受模块代理下载阻塞。

### AI Summary MVP

- 新增 FastAPI AI Service。
- 新增 deterministic/OpenAI/Ollama provider。
- 新增 SQLite `ai_notes` 持久化。
- 新增 Memos created/updated Webhook 触发总结。
- 新增 Docker Compose 和基础 API/架构文档。

## 记录规则

每个完成的功能切片追加一节，至少包含：日期、用户可见变化、验证命令/结果、阻塞项、commit。不要修改历史事实，用新条目纠正状态。
