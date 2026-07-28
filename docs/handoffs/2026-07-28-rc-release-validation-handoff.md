# DevMemo AI RC 发布验证交接（2026-07-28）

## 完成的真实外部验证

- 已推送分支 `codex/devmemo-ai-mvp`；[PR #1](https://github.com/ToYOhin/devmemo-ai/pull/1) 的 Backend、Frontend 和 AI Service workflow 全部通过。Backend 包含 Store SQLite/MySQL/PostgreSQL 矩阵与 golangci-lint。
- 第一轮 [GHCR canary](https://github.com/ToYOhin/devmemo-ai/actions/runs/30320815675) 失败的实际根因是 `ghcr.io/ToYOhin/devmemo-ai` 含大写字符，不符合 OCI repository 格式；已将 canary/release workflow 固定为 `ghcr.io/toyohin/devmemo-ai`。
- 修复后的 [GHCR canary](https://github.com/ToYOhin/devmemo-ai/actions/runs/30321064397) 成功完成 `linux/amd64`、`linux/arm64` 构建、manifest 合并和 runner-side `docker buildx imagetools inspect`。
- 已在明确授权下创建私有 prerelease [v0.1.0-rc.1](https://github.com/ToYOhin/devmemo-ai/releases/tag/v0.1.0-rc.1)，tag 指向 `1ae359672680abde5578dd839649d3da95a5f62b`。其 [Release workflow](https://github.com/ToYOhin/devmemo-ai/actions/runs/30321310211) 成功构建并上传六个原生资产、`checksums.txt`，并发布多架构 GHCR 镜像。
- 本机低负载复核从该 Release 下载 Windows ZIP 和 `checksums.txt`；SHA-256 为 `80e03c07891c69e923417437d08d30356fb17fbbe74451e00f989cac1fa6ffaf`，与清单一致。解压后的 `devmemo-ai.exe --help` 成功；六个二进制资产名称与 checksum 清单一一对应。下载与解压产物保留在 `H:\codex-output\devmemo-rc-asset-verify-20260728`。

## 仍然存在的外部治理边界

- 这是 private prerelease，不是公开或稳定发布；不得将其宣传为正式 GA。
- 仓库仍为 private，Actions secrets 数为 0，`RELEASE_PLEASE_TOKEN` 尚未配置；私密漏洞报告渠道尚未确认可供外部研究者使用。
- 本机 GitHub OAuth token 可登录 GHCR 但没有 private Packages `read:packages`，直接 `imagetools inspect` 返回 403。GitHub runner 的 inspect 已成功，因此这是维护者本地凭据范围问题，不是 workflow 或镜像发布失败。不要把 token 写入文件、secret、日志或 issue。
- 不得自行改变仓库可见性、创建长期 PAT、推 stable tag 或创建正式 Release；这些是维护者的独立外部决策。

## 下一步（仅在明确授权时）

1. 维护者配置可轮换、最小权限的 `RELEASE_PLEASE_TOKEN`，并确认外部私密漏洞报告渠道与公开可见性策略。
2. 单独授权 stable tag/Release 后，重新确认 Release Please 只使用 DevMemo AI 命名、GHCR `ghcr.io/toyohin/devmemo-ai` 和可回滚的发布说明。
3. 继续保持默认 deterministic + memory、`AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、`AI_VECTOR_STORE=memory` 与 `AI_PUBLIC_CHUNK_RETRIEVAL=false`；本次没有修改 Memos 原始数据、AI SQLite、Context Pack 或公共 API。
