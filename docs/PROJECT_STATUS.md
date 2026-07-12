# DevMemo AI 项目状态

更新时间：2026-07-12

## 当前阶段

Phase 0 基础环境、Phase 1 AI 总结 MVP、Phase 2 模板解析和结构化持久化已完成；下一阶段是 Memos React 模板展示/复制 UI。

## 当前事实

- 工作区：`H:\DevMemoAI`
- 当前分支：`codex/devmemo-ai-mvp`
- Memos 基线：`v0.29.1`
- 上游 remote：`https://github.com/usememos/memos.git`
- 私人仓库：`https://github.com/ToYOhin/devmemo-ai`
- Go：`G:\Go`，版本 `go1.26.2 windows/amd64`
- Go 工作区：`G:\GoWorkspace`
- Docker Desktop：可用

## 已完成

- 独立 FastAPI `ai-service`。
- deterministic/OpenAI/Ollama provider 边界。
- `/api/ai/summarize` 和 Memos Webhook。
- SQLite `ai_notes` 持久化。
- Docker Compose：Memos、AI Service、Qdrant、Ollama。
- 开源组件采用记录、二次开发路线和目标目录结构。
- Windows 验证脚本：`scripts/verify-devmemo.ps1`。
- 本文档体系与下一步 Prompt 体系。
- Phase 2 已新增 `CodeSnippet`、`BugReport`、`ParsedMemo` 领域模型和 Markdown/frontmatter 解析器。
- Memos Webhook 已返回 `memo_type` 与结构化 `template`，普通/空 Memo 保持兼容。
- `memo_templates` 已支持按 `memo_id` upsert 和读取 API，保留 `raw_content`。

## 最近验证

```text
go version                         PASS
AI Service pytest                  15 passed
docker compose config              PASS
scripts/verify-devmemo.ps1         DEVMEMO_VERIFY_OK
graphify AST                       26,211 nodes / 41,155 links
graphify semantic supplement       10 nodes / 12 edges
```

## 未完成或阻塞

- `go test ./...` 尚未完成：Go 模块代理下载在本机超时，不能据此判断为代码失败。
- Docker 镜像构建曾因 Docker Hub 网络连接失败，尚未完成完整容器启动烟测。
- Phase 2 模板解析和结构化模板持久化已完成；Memos React UI 尚未实现。
- Phase 3 FastEmbed、qdrant-client、RAG 尚未加入运行时依赖。
- Webhook 尚未增加共享密钥/HMAC。

## 下一步

执行 [docs/prompts/NEXT_STAGE_PROMPT.md](prompts/NEXT_STAGE_PROMPT.md)，推进 Memos React 模板展示/复制 UI。
