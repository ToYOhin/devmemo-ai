# 运维指南

[English](operations.md)

本文面向自托管 DevMemo AI。Memos 仍是 Memo 内容、身份和权限的事实来源；升级或迁移主机前
必须先备份。

## 启动与健康检查

```powershell
docker compose config
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health
```

默认堆栈只启动 Memos 与 AI Service；Qdrant、Ollama 仍是可选 profile。`restart:
unless-stopped` 允许 Docker 在 daemon 或主机重启后恢复已启动服务；有意停止时使用
`docker compose down`。

首次排障可使用 `docker compose logs --tail=200 memos ai-service`。不要将
`AI_WEBHOOK_SECRET`、`AI_OPS_TOKEN`、`AI_PUBLIC_CHUNK_SECRET` 或 provider key 写入
日志、工单或 issue。

## 备份与恢复

应同时备份以下 named volume：

- `memos-data`：Memos 的权威数据、用户和权限。
- `ai-data`：AI 派生摘要、模板、Insight 审核状态和 outbox 审计状态。

启用可选 Qdrant profile 时，需要决定备份 `qdrant-data`，或在恢复后重建派生索引。
`ai-model-cache` 和 `ollama-data` 是模型缓存，不能作为业务数据的唯一副本。

为获得一致备份，应停止堆栈，或使用能保证两个数据卷一致性的存储快照机制。归档前用
`docker volume ls` 记录实际 volume 名称，并对备份进行加密和访问控制。

恢复时先停止堆栈，将 `memos-data` 与 `ai-data` 恢复到原 volume 名称，再启动服务。先验证
Memos 登录与可见性，再验证 `GET /health`、AI 详情页和已接受 Insight 的 Context Pack。
不要将生产备份恢复到公网测试环境。

## 升级与回滚

1. 阅读目标 Memos 版本说明并备份所需 volume。
2. 一次只更新一个上游 Memos tag 或一组固定依赖。
3. 部署前运行 `docker compose config`、AI Service 测试、Web 检查和相关 Go 检查。
4. 用 `docker compose up -d --build` 重建，随后检查 Memos 与 AI health。
5. 若 smoke 检查失败，回滚镜像/配置；涉及数据迁移时从已验证备份恢复。

`docker-compose.local-webhook.yml` 只适用于受控的本地 Docker 拓扑，不能用于公网或多用户部署。

## 实验性 Agent 运维边界

除非正在经过明确审查的本地拓扑中测试 Evidence Answer，否则保持
`AI_AGENT_ENABLED=false`。A4 lifecycle outbox 与 AI ledger 仍是 dormant 证明，不能据此
启用 dispatcher、worker、自动索引或持久化向量库。未来 rollout 必须先具备权威可见性检查、
对账与重建步骤、有界重试、多实例共享 replay store，以及经过测试的关闭并重建回滚方案。

## 安全边界

除非确有可选 adapter 需求，否则保持默认 deterministic + memory。继续保持
`AI_PUBLIC_CHUNK_RETRIEVAL=false`，直到真实 trusted gateway、Memos visibility mapping、
受控灰度和经过测试的关闭/回滚路径全部具备。Context Pack 只存在于浏览器内存中，不能视为
服务端导出通道。
