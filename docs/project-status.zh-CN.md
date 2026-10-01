# DevMemo AI 当前交付状态

[English](project-status.md) · [整体路线](roadmap.md) · [项目结构](structure.md)

状态快照：**2026-10-01**。本文是当前产品与证据入口，不是实时 CI 看板；发布判断仍须核对
现场 Git/GitHub。目标是可讲清、可演示的个人/简历项目，不按商业化多实例平台推进。

## 已实现范围

| 模块 | 当前实现 | 验证边界 |
| --- | --- | --- |
| Memos 核心 | Go + 内嵌 React，身份、可见性、Memo/附件持久化 | Windows 候选合成账号/数据的真实 HTTP runtime，不代表浏览器交互验收 |
| Windows 交付 | 当前用户核心安装、快捷方式、升级回滚、异步卸载保留数据 | 本机候选 51/51 检查、`cmd/memos` 22 个顶层测试；不包含 AI sidecar |
| Evidence Answer | 认证同源 BFF、唯一只读 `search_memos`、服务端引用 | 受限单机 opt-in；合成证明不代表真实用户模型质量 |
| AgentRun | 固定同步 `project_summary`、可见 Memo revision、创建者 Markdown artifact | 有界 runtime + 可选报告 Finalizer；无自由任务/后台 worker/写回 |
| Provider 管理 | 设置界面、掩码 API、SQLite 加密凭据、动态 Agent Provider | 配置/存储/失败合成测试；旧摘要/chat 仍用环境配置，不受 Agent 设置覆盖 |
| Lifecycle/RAG | 源端 outbox、派生 ledger、当前权威 rehydration、可选 Qdrant 组合 | 已实现默认关闭的单机 opt-in，不代表多实例验收 |
| 依赖安全 | PR #25/#28 已合并修复 | 当日 GitHub API 开放 Dependabot 告警 **0 条**，不是永久无漏洞保证 |

默认继续使用 deterministic/memory，Agent、lifecycle、自动索引和公共 chunk retrieval 默认关闭。
配置见 [AI 使用指南](../README_AI.zh-CN.md)。

## 证据身份

- 最近已发布稳定版：[v0.3.0](https://github.com/ToYOhin/devmemo-ai/releases/tag/v0.3.0)。
  **v0.4.0 尚未发布**；main 推送、元数据和候选验收不等于 Release。
- 修复前源码 `ca334b64fc3e427a44fc0d78a7f4c800c6c94379` 的
  [Backend/Windows](https://github.com/ToYOhin/devmemo-ai/actions/runs/36809392669)、
  [Frontend](https://github.com/ToYOhin/devmemo-ai/actions/runs/36809392743)、
  [AI Service](https://github.com/ToYOhin/devmemo-ai/actions/runs/36809392595)、
  [Proto](https://github.com/ToYOhin/devmemo-ai/actions/runs/36809392616)、
  [Canary](https://github.com/ToYOhin/devmemo-ai/actions/runs/36809392603) 均成功。
  这些运行不能代表后续提交；Canary 仅为云端 Linux 镜像证据。
- 安装器修复源码：`aa5cd355e635139a72ca17035e94cff9443df116`。
  差异与已验收候选输入一致；22 项本地 Go 回归在提交前通过，推送后 exact-head CI 独立核对。
- 候选输入：修复前 SHA + 补丁 SHA-256
  `32acb3f9389953fb9677f745b03e348c05fbc554542bce4a05894e35698d94bc`。
  内嵌版本 `0.4.0`、commit 为修复前 SHA，Go build info 标记 `vcs.modified=true`，
  **不是干净 tag 构建**。
- 便携 EXE/setup/ZIP 内程序 SHA-256：
  `6401b88c74bec55ffccc2683c767de877398f3f325c5293d1b488aa01ae8beb0`。
  ZIP SHA-256：`d598a79de29b8c9384c905b6ec4933e904dce5d0e94df10d06b446daf2e146a6`。
  仅编译一次 Go 候选，复用已核验生产 Web 资源，没有重建前端。

本机验收使用真实 HKCU 登记、COM 快捷方式与独立合成数据目录，覆盖安装、两次显式启动
已安装程序、锁定快捷方式导致的升级失败/回滚、真实卸载 worker 清理及数据保留。
没有确认安装成功对话框触发浏览器自动打开。详细日志、合成数据、本机交接留在 Git 外。

## 推进问题与剩余事项

历史切片的“未接线”被当作当前状态，导致重复推进已完成的 R5/R7 闸门；结构图未收录
设置/Finalizer、Web 树重复；源码 CI、合成测试、包执行与发布事实混用；商业化目标挤占
简历演示收尾。现将当前状态、目标路线、带日期的证据分开维护。

| 优先级 | 事项 | 完成条件 |
| --- | --- | --- |
| 当前收尾 | exact-head CI 与仓库状态 | 核对推送源码门禁、main/远端一致、工作树干净和带日期的告警快照 |
| 下一产品任务 | 可复现的一体化 Agent 演示 | 合成记录 → 设置 → 回答/报告 → 失败回退；服务缺失如实提示，若主张 UI 通过则提供真实界面证据 |
| 小型后续 | PowerShell 本地化错误详情乱码 | 定向编码回归、详情可读；安装失败识别与回滚功能已通过 |
| 可选分发验证 | 更广安装与包验证 | 浏览器/快捷方式自动启动、端口冲突、便携迁移、干净 tag 多平台包、下载后未签名行为等，见 [发布指南](releases/v0.4.0.zh-CN.md) |
| 当前范围外 | worker、approval、写回、真实用户 Provider 质量、多实例 authority | 新产品范围与独立证据，不顺带启用 |

纯文档整理无需重建。[开发指南](development.md) 定义改动区域检查；历史 Phase/R5/R6
记录保留当时证明，不产生重复执行已完成任务的要求。
