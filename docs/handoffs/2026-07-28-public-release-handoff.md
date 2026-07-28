# DevMemo AI 公开稳定发布交接（2026-07-28）

## 已完成

- [PR #1](https://github.com/ToYOhin/devmemo-ai/pull/1) 已合并到 `main`，merge commit 为 `75ce0de5e69eddd66bdab15f2b6bf278a222ad6f`。其真实 Backend、Frontend 和 AI Service Actions 门禁均通过。
- 稳定 [v0.1.0 Release](https://github.com/ToYOhin/devmemo-ai/releases/tag/v0.1.0) 已发布；[Release workflow](https://github.com/ToYOhin/devmemo-ai/actions/runs/30322636815) 成功构建 Linux amd64/arm64/armv7、macOS amd64/arm64、Windows amd64 六个资产和 `checksums.txt`，并发布 `v0.1.0`、`0.1`、`stable` 多架构镜像标签。
- 本机低负载下载稳定 Windows ZIP 后，SHA-256 `fbb406355fdae63707585d59557374e51064be40bd8496bd26cf9cd5b40b054f` 与 Release 清单一致，解压后的 `devmemo-ai.exe --help` 成功。验证产物保留在 `H:\codex-output\devmemo-stable-asset-verify-20260728`。
- 仓库已切换为 public；GitHub private vulnerability reporting 已启用，读取 API 返回 `enabled=true`。这符合 GitHub 对公开仓库私密漏洞报告的能力边界。
- `RELEASE_PLEASE_TOKEN` 不再是发布阻塞：缺失时 Release Please workflow 安全跳过，专用可轮换 PAT 只在需要自动 proposal 时再配置；没有保存或暴露个人 OAuth token。

## 唯一未完成项

- GHCR Container package `ghcr.io/toyohin/devmemo-ai` 仍独立保持 private。仓库公开后，以未登录 Docker 执行 `docker buildx imagetools inspect ghcr.io/toyohin/devmemo-ai:stable` 返回 401；因此不得宣称镜像已可公开拉取。
- 当前 GitHub CLI OAuth token 没有 `read:packages`/`write:packages`。scope refresh 和浏览器交互式授权均未在本会话完成；未读取或记录任何凭据。

## 下一步（需要 Packages 管理权限）

1. 登录 GitHub 后打开 `https://github.com/ToYOhin/devmemo-ai/pkgs/container/devmemo-ai/settings`，在 package visibility 中选择 **Public** 并确认。
2. 退出 Docker 登录或使用未登录环境运行：

```powershell
docker buildx imagetools inspect ghcr.io/toyohin/devmemo-ai:stable
```

3. 确认输出含 `linux/amd64`、`linux/arm64` 和 `linux/arm/v7` 后，更新本文件与状态文档；除此以外没有默认产品开发任务。

## 保持不变

- Memos 是 Memo/权限事实源；AI Service 只保存派生 SQLite 状态。
- 默认保持 deterministic + memory、`AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、`AI_VECTOR_STORE=memory`、`AI_PUBLIC_CHUNK_RETRIEVAL=false`。
- Context Pack 仍是浏览器内存中的 accepted-only、安全字段输出；本次没有改动 Memos 原始数据、AI SQLite、公共 API、collection、volume 或 gateway rollout。
