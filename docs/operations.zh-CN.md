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

除非显式使用文档限定的单机 Agent 路径，否则保持 `AI_AGENT_ENABLED=false`。
lifecycle/outbox/ledger/rehydration 已有 opt-in composition，不再只是未接线证明；但不是
默认启用或多实例 authority。受控拓扑见 [AI 指南](../README_AI.zh-CN.md) 和
[R5 验收](r5-acceptance.zh-CN.md)。worker、自动索引、真实数据迁移、共享 replay/rebuild
authority 属于独立扩展，不作为简历演示前置条件。

保存 Agent 凭据时，AI SQLite 与 `AI_AGENT_PROVIDER_MASTER_KEY` 分开备份。
升级不要重新生成主密钥，否则已有密文无法解密。管理员保存配置只作用于 Agent 路径，
旧 AI 路由仍使用环境配置。

## Windows 核心安装与卸载

程序位于 `%LOCALAPPDATA%\Programs\DevMemoAI`，Memo 数据/附件位于
`%LOCALAPPDATA%\DevMemoAI\data`。一致备份前停止本安装程序；自定义便携数据目录不会自动迁移。

安装/升级失败尽可能恢复旧 EXE；部分更新的快捷方式/注册表可能需要重新安装修复。
PowerShell 执行失败不会再被当作安装成功。卸载先调度隐藏 worker，关闭控制器对话框后，
查看其给出的 `%LOCALAPPDATA%\DevMemoAI\uninstall-<pid>.log`。
`STARTING`/`STARTED` 不是完成；`COMPLETED` 表示程序/快捷方式/登记清理成功，`FAILED`
记录失败。Memo 数据保留；实际文件/快捷方式清理成功前保留卸载登记。

核心包不安装/启动 AI Service 或模型运行时；当前候选证明及未验证的浏览器/分发事项见
[v0.4.0 指南](releases/v0.4.0.zh-CN.md)。

## 安全边界

缩略图生成会先在 1 MiB 的头部探测预算内检查图片尺寸，再进行完整解码，源图片最多允许
5000 万像素。无效、超限或无法在头部预算内确认尺寸的图片，沿用原文件回退策略；这不代表
拒绝上传，也不会删除附件。TIFF 调色板检查依赖已固定版本的 `golang.org/x/image` 解码器。
图片处理使用 `github.com/kovidgoyal/imaging v1.6.5`，替换受 GHSA-q7pp-wcgr-pffx 影响的依赖。
其扫描器可处理所有单字节调色板索引；合成回归覆盖无效索引、TIFF 拒绝解码和原文件回退，
同时保留 EXIF 自动方向校正及 Lanczos 缩放。

除非确有可选 adapter 需求，否则保持默认 deterministic + memory。继续保持
`AI_PUBLIC_CHUNK_RETRIEVAL=false`，直到真实 trusted gateway、Memos visibility mapping、
受控灰度和经过测试的关闭/回滚路径全部具备。Context Pack 只存在于浏览器内存中，不能视为
服务端导出通道。
