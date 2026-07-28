# DevMemo AI 发布前 CI 收敛交接（2026-07-28）

## 本次完成

- 修复 PR #1 的 Store migration CI：浮动 `neosmemo/memos:stable` 已改为固定 `neosmemo/memos:0.26.2` fixture；原失败是 stable 生成 schema `0.30.1`，而当前源码只到 `0.28.1`，触发拒绝降级。
- `TestMigrationFromPinnedFixtureVersion` 在受限 CPU 的真实 Docker SQLite 路径中通过：fixture schema `0.26.5` 迁移至 `0.28.1`，并验证迁移后写入。
- 后端 workflow 的 golangci-lint timeout 从 `3m` 调整为 `5m`。此前远端在 `0 issues` 后仍以 timeout code 4 失败；没有放宽 lint 规则。
- 复核本仓库仍为 private，Actions secrets API 返回 0，默认 workflow permissions 为 read；release/package 作业已有独立最小写权限。private vulnerability reporting 不能在当前状态下作为已验证公开报告渠道。

## CPU 与验证边界

- Docker Desktop 仅用于一次串行 SQLite fixture 测试；全驱动 Store 门禁因本机 CPU 限制被主动停止，未得到 pass/fail 结论。未运行 Web、AI Service 或全量 Go 门禁。
- `backend-tests.yml` YAML 解析和 `git diff --check` 通过。真实 GitHub Actions 只有在维护者授权 push 后才能验证。

## 仍为 NO-GO 的外部条件

1. 设置可轮换的 `RELEASE_PLEASE_TOKEN` Actions secret；不得复用本机登录 token 或记录其值。
2. 在公开仓库前决定可见性，并启用/验证面向外部研究者的私密漏洞报告渠道。
3. 授权 push 后，观察 Backend/Frontend/AI Service CI 真实通过，特别是 MySQL/PostgreSQL Store 矩阵和 golangci-lint。
4. 只有再次取得明确发布授权后，才能让 Release Please tag、创建 GitHub Release 或推送 GHCR 镜像。

详见 [`docs/release-preflight.md`](../release-preflight.md)。保持 Memos/AI 权限边界、默认 AI 配置、Context Pack 安全边界和 `AI_PUBLIC_CHUNK_RETRIEVAL=false` 不变。
