# 原生 Agent 演示

[English](native-agent-demo.md) · [AI 使用指南](../README_AI.zh-CN.md)

用已有便携 Memos EXE 和 `ai-service/.venv` 启动简历演示，无需 Docker、模型或 API key。
EXE 必须包含当前 AgentRun / Provider BFF API；核心安装包本身不包含 Python AI Service。
Python 环境按 [开发指南](development.md) 安装锁定依赖。脚本不构建、不下载依赖、不打开浏览器。

在仓库根目录运行，将 `-MemosExe` 替换为已有的便携 EXE 路径，不能传入 Setup 安装器：

```powershell
.\scripts\start-agent-demo-native.ps1 -MemosExe .\build\DevMemoAI.exe
```

脚本依次启动两个仅监听 `127.0.0.1` 的服务，自动选择空闲端口并打印演示地址和合成账号。
每次创建独立数据目录，生成两条中文合成项目记录，保存 deterministic 设置，验证带引用回答和
项目总结。终端保留运行；手动打开打印的地址，使用打印的 `demo` 账号及随机密码登录。
按 `Ctrl+C` 结束本次两个进程，保留合成数据与报告，不影响其他服务。

仅执行 HTTP 验证并自动结束：

```powershell
.\scripts\start-agent-demo-native.ps1 -MemosExe .\build\DevMemoAI.exe -VerifyOnly
```

该模式覆盖 25 项检查，包括管理员设置、连接测试、真实 Memo Webhook 索引、服务端引用、
连续两份报告、同一请求重放、下载正文 SHA-256、私有 Memo 隔离与创建者报告权限。
它还停止本次 AI Service，核对 Agent 返回 503、普通 Memo 仍可读取，然后结束 Memos。
成功标记为 `DEVMEMO_NATIVE_DEMO_OK`；失败以非零状态结束并保留日志。

回退演示临时保存一项未允许 Memo 数据使用的本地 Provider 配置，由既有数据使用检查在
创建/调用 Provider 前拒绝，报告明确标记 `provider_unavailable` 与 deterministic fallback。
随后恢复 deterministic 设置。这个合成配置失败不代表真实 Provider、网络超时或模型质量验收。

数据、日志和报告放在 Git 忽略的 `.devmemo-local/runtime/native-agent-demo-*`，核心数据与
AI SQLite 分开。`project-summary.md` 为正常报告，`project-summary-fallback.md` 为回退报告；
`evidence-answer.json` 与 `verification.json` 记录引用、检查、二进制摘要和进程退出状态。
登录 token 和临时委托/加密密钥只保留在进程内存中，不复用原有环境中的 Provider 凭据。

可用 `-MemosPort 5231 -AiPort 8001` 固定端口；已占用端口会明确失败，不停止原有服务。
默认部署开关不变，低资源模式为 `GOMAXPROCS=1`、Python 单 worker 和数值库单线程。

HTTP 验证不能替代界面验收。显示“项目总结”/Evidence Answer 面板还需要已有 Web 资源包含
AI UI opt-in（`VITE_AI_SERVICE_URL`）；启动脚本不能改变已内嵌资源的构建时开关。
若面板缺失，HTTP 报告依然可查看，但不能宣称完整 UI 演示已通过。
