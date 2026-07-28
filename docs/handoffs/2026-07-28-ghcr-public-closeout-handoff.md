# DevMemo AI GHCR 公开可用性收尾（2026-07-28）

## 结论

公开发行的最后一个可用性缺口已经闭环。GitHub Container package `ghcr.io/toyohin/devmemo-ai` 已在维护者 GitHub 会话中从 private 改为 public；未登录 Docker 客户端随后成功执行：

```powershell
docker buildx imagetools inspect ghcr.io/toyohin/devmemo-ai:stable
```

返回 OCI image index `sha256:86a099ceb6e8752aceec8517574840ec0df97730945d0843b5b0305df782dd06`，并明确包含：

- `linux/amd64`
- `linux/arm64`
- `linux/arm/v7`

输出中另有每个平台的 `unknown/unknown` attestation manifest；它们不是缺失的平台，也不改变上述三种可拉取镜像架构的结论。

## 未改变的边界

- 未重打 tag，未重发 `v0.1.0` GitHub Release，未改动运行时代码、Compose、默认 AI 配置或 public-chunk flag。
- 未请求、导出或保存密码/token。现有 GitHub CLI OAuth 仍无 Packages scope；公开化由已有维护者浏览器会话完成。
- 默认继续是 deterministic + memory、`AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、`AI_VECTOR_STORE=memory` 和 `AI_PUBLIC_CHUNK_RETRIEVAL=false`。
- Context Pack 继续是 accepted-only、显式来源、浏览器内存输出；不暴露 raw content、Webhook payload、secret 或 chunk content。

## 当前发布事实

- 仓库为 public。
- GitHub Release `v0.1.0` 已发布，非 draft、非 prerelease。
- GitHub private vulnerability reporting 已启用。
- GHCR `stable` 已由未登录客户端验证为可公开读取的三架构 OCI index。

## 后续

发行收尾已完成，当前没有默认实现任务。下一切片必须由用户明确选择：恢复有效 Memos 登录态后的 Phase 11 只读复核、具备真实 gateway/visibility/rollback 前提后的 route A 评估，或新的最小产品 proposal。只在用户明确要求时才 commit、push、打 tag 或发布。
