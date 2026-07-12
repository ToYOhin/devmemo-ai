# 2026-07-12 Phase 2 模板解析交接

## 本次完成

- 新增 `ai-service/app/domain/models.py`：`CodeSnippet`、`BugReport`、`ParsedMemo`。
- 新增 `ai-service/app/services/content_parser.py`：frontmatter、type 标记、代码 fence、Bug Report sections 和内联字段解析。
- Memos Webhook 返回 `memo_type`、`template`、`parse_errors`；普通/空 Memo 不阻断。

## 验证

- AI Service：`10 passed`。
- `scripts/verify-devmemo.ps1`：`DEVMEMO_VERIFY_OK`。
- `git diff --check`：待本轮文档更新后执行。

## 下一步

实现 AI Service 自有 `memo_templates` 持久化和按 `memo_id` 读取 API，不修改 Memos 核心表；入口见 `docs/prompts/NEXT_STAGE_PROMPT.md`。

## 相关提交

- `d6578d0 feat(ai): add developer memo template parser`
- `987a95f feat(ai): expose parsed memo templates in webhook`
- `dffcdf2 fix(ai): parse inline template fields`
