# 新窗口启动 Prompt

```text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要重新从零设计。

第一步读取：
1. docs/PROJECT_STATUS.md
2. docs/HANDOFF.md
3. docs/DOC_UPDATE_POLICY.md
4. docs/prompts/NEXT_STAGE_PROMPT.md
5. docs/roadmap.md
6. docs/structure.md

然后执行：
Set-Location H:\DevMemoAI
git status --short --branch
git log --oneline -5
.\scripts\verify-devmemo.ps1

以 PROJECT_STATUS 和最新 git 状态为准。如果文档与代码不一致，先报告差异，再选择最小修复。当前默认任务是 NEXT_STAGE_PROMPT 中的 Phase 2c Memos React 模板展示/复制 UI 切片。

必须遵守：
- 不重写 Memos 核心，不直接修改 Memos 数据库迁移。
- 每个小步先测试、再进入下一步。
- 完成时更新 PROJECT_STATUS、CHANGELOG_AI、HANDOFF、NEXT_STAGE_PROMPT，并按需更新 DECISIONS/ROADMAP/STRUCTURE/API。
- 最后给出验证结果、未验证部分、commit 和下一步 Prompt。
```
