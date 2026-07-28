# DevMemo AI 开源发布基础设施交接（2026-07-28）

## 完成范围

本切片只完成发布基础设施，没有新增产品功能、API、数据库、依赖或默认 AI 行为。

- `README.md` 说明 DevMemo AI 是基于 Memos 的非官方自托管开发者知识库，包含用途、快速起步、帮助、维护者、贡献和许可证入口。
- `NOTICE` 与 `UPSTREAM.md` 区分上游 Memos `v0.29.1` 和本项目的下游维护范围；根目录社区文件补齐贡献、支持、治理与行为准则。
- `SECURITY.md` 仅指向本仓库的 GitHub private advisory 路径，并明确在公开发布前必须启用该通道或提供等价私密渠道。
- 默认 `docker-compose.yml` 删除 Memos `--allow-private-webhooks`；`docker-compose.local-webhook.yml` 是唯一允许本机 Docker service hostname 私网放行的显式开发 override。
- 发布/安装/CI 使用 DevMemo 自有 `devmemo-ai` 二进制、资产和 GHCR 命名空间；新增 `.github/workflows/ai-service-tests.yml`。上游 Go module import path 故意保持不变。

## 已验证

```powershell
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.local-webhook.yml config --quiet
```

两种 Compose 配置都通过；默认配置不包含 `--allow-private-webhooks`，叠加 override 后才包含。`scripts/install.sh` 已在运行中的 AI Service 容器内完成 POSIX `sh -n` 和 `--help` 检查（宿主机无可用 POSIX shell）。工作流做了缩进/命名空间静态检查，`git diff --check` 通过。

本次没有修改应用代码，故没有重跑 AI Service、Web、Go 全量门禁；也没有启动 Qdrant/Ollama profile、创建 Memo/Insight 或读取认证凭据。

## 正式公开发布：仍为 NO-GO

以下外部条件尚未完成，不能把本次配置改动写成“已发布”：

1. 修复既有后端 CI 的 store migration 超时/版本不匹配。
2. 在目标 GitHub 仓库配置 Release Please 所需 token、Packages 写入权限和仓库 Actions 权限，并在真实 CI 中验证。
3. 启用 GitHub private vulnerability reporting，或在公开前建立并公布等价私密安全联系渠道。
4. 在真实仓库确认 DevMemo GHCR 镜像、安装资产、release notes 和回滚路径；未经用户明确授权不得 push、打 tag 或发布。

## 不变量

- Memos Go server/store/proto 仍是 Memo 与权限事实源；AI Service 只存派生 SQLite 状态。
- 保持 `AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、`AI_VECTOR_STORE=memory`、`AI_PUBLIC_CHUNK_RETRIEVAL=false`；FastEmbed/Qdrant 仍是显式 adapters/profiles。
- Context Pack 仍只在浏览器内存中处理显式可见 Memo、accepted insights 与安全字段；不写 SQLite、不连接 Qdrant、不启动 worker。
- Phase 10 route B 已完成且不重复；Phase 11 当前登录态下的真实只读详情页/系统剪贴板复核未完成；route A 仍缺受信任 gateway、可见范围映射和回滚证据。

## 建议下一步

若用户要继续发布准备，先在不发布、不 push 的前提下诊断既有后端 CI migration 失败和 GitHub 仓库设置，给出最小修复提案与验证计划。不要恢复默认私网 Webhook 放行，也不要复用上游发布命名空间。
