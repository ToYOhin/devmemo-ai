# DevMemo AI 发布前检查清单

此清单用于准备公开发布，不会自行创建 tag、GitHub Release、GHCR 镜像或修改仓库可见性。

## 当前已完成

- README、MIT/upstream NOTICE、贡献、支持、治理、行为准则和安全策略已就位。
- 默认 Compose 禁止私网 Webhook；仅显式本机 development override 可以放行。
- 发布资产和镜像命名空间使用 `devmemo-ai` 与固定小写的 `ghcr.io/toyohin/devmemo-ai`。
- Store migration fixture 已固定为 `neosmemo/memos:0.26.2`；低 CPU SQLite 验证通过 `0.26.5 -> 0.28.1`。
- golangci-lint timeout 已从三分钟调整为五分钟；规则集没有放宽。
- 真实 GitHub PR CI 已通过 Backend、Frontend 与 AI Service workflow，包含 Store 的 SQLite/MySQL/PostgreSQL 矩阵和 golangci-lint。
- 手动 GHCR canary 已通过 amd64/arm64 构建、manifest 合并和 runner-side `imagetools inspect`；首次运行暴露并修复了 OCI repository 大小写限制。
- 私有 RC `v0.1.0-rc.1` 已成功生成六个原生二进制、`checksums.txt` 与多架构镜像；Windows ZIP 的 SHA-256、解压和 `devmemo-ai.exe --help` 已本机低负载复核。

## 维护者必须完成的 GitHub 设置

1. 如需自动生成 release proposal，维护者可在 GitHub 创建一个最小权限、可轮换的 token，并将它保存为 Actions secret `RELEASE_PLEASE_TOKEN`。不得把个人登录 token、密码或 token 值写入代码、文档、日志或 issue。未配置时 Release Please 会安全跳过，手工稳定 tag/release 不受阻塞。
2. 在决定将仓库公开前，确认 `SECURITY.md` 中的私密报告渠道可供外部研究者使用；公开后立即在 GitHub 仓库安全设置中启用并复核 private vulnerability reporting，或先提供等价的专用私密联系渠道。
3. 复核 Actions 的最小权限原则：默认 token 可以保持 read；`release.yml` 和 canary workflow 的 GHCR 作业需要自己的 `packages: write`，GitHub Release 作业需要自己的 `contents: write`。
4. 确认仓库可见性、许可证、维护者联系方式和支持范围已由维护者人工审阅。公开可见性是不可逆的外部发布决策，必须单独确认。

## 授权 push 后的真实验证

1. Push 已提交的 CI 修复，确认 PR 的 Backend Tests、Frontend Tests 和 AI Service Tests 都通过。
2. 复核 golangci-lint 不再在 `0 issues` 后超时，并确认 Store 的 SQLite/MySQL/PostgreSQL 矩阵完整通过。
3. 若配置了该可选 token，确认 Release Please 只生成 DevMemo AI 自有版本、changelog 和 tag 提案；未配置时确认 workflow 的安全跳过不影响手工稳定发布。
4. 只有用户明确授权发布后，才创建或接受稳定版本 tag；随后确认 GitHub Release 资产的二进制名为 `devmemo-ai`、GHCR 镜像位于 `ghcr.io/toyohin/devmemo-ai`、安装脚本校验和可用，并记录回滚步骤。`v0.1.0-rc.1` 已作为私有 prerelease 验证资产链路，不能替代正式发布批准。

## 保持不变的产品边界

- Memos 仍是 Memo 与权限事实源；AI Service 只保存派生 SQLite 状态。
- `AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、`AI_VECTOR_STORE=memory`、`AI_PUBLIC_CHUNK_RETRIEVAL=false` 保持默认。
- Context Pack 仍仅在浏览器内存中使用显式可见 Memo、accepted insights 与安全字段。
