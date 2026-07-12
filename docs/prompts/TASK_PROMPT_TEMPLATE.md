# 任务 Prompt 模板

```text
工作区：H:\DevMemoAI
任务名称：[简短名称]
目标：[完成后可观察的行为]

先读：
- docs/PROJECT_STATUS.md
- docs/HANDOFF.md
- docs/DOC_UPDATE_POLICY.md
- docs/prompts/NEXT_STAGE_PROMPT.md

范围内：
- [文件/模块/行为]

范围外：
- [明确不修改的核心、UI、数据库或部署边界]

实现策略：
- 先做最小垂直切片。
- 每一步完成后运行相关测试。
- 保持旧 API/启动命令兼容。

验证：
- [命令 1]
- [命令 2]
- git diff --check

完成后：
- 更新 docs/PROJECT_STATUS.md
- 追加 docs/CHANGELOG_AI.md
- 更新 docs/HANDOFF.md
- 生成下一步 docs/prompts/NEXT_STAGE_PROMPT.md
- 按需更新 docs/DECISIONS.md、docs/roadmap.md、docs/structure.md、docs/api.md
- 创建独立 commit

停止条件：[需要用户决定或外部环境改变时停止]
```
