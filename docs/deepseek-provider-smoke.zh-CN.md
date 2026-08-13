# DeepSeek Provider smoke

本 smoke 使用合成证据验证真实 DeepSeek adapter。它不会启动 Docker、写入 Memo、使用真实用户数据，
也不会持久化 API key。

## 验证内容

- `AI_PROVIDER=deepseek` 会选择独立 adapter。
- 请求使用 OpenAI-compatible `/chat/completions` endpoint。
- 固定关闭 thinking、要求 JSON 输出，并把输出限制为 1,200 token。
- 响应必须是有效的 `grounded-answer-result-v1` JSON，并绑定到提供的合成 citation。
- transport error、HTTP 408/429 和服务端错误最多重试一次；其他客户端错误立即失败。

## 运行

先创建 `ai-service/.venv` 并安装锁定依赖，然后执行：

```powershell
Set-Location <repository-root>
.\scripts\smoke-deepseek-provider.ps1
```

在掩码提示符中输入 API key。脚本只在当前进程中持有凭据，在 `finally` 中恢复原有 Provider
环境变量，并且只输出有界的合成验证 metadata。成功结果类似：

```json
{"status":"passed","provider":"deepseek","version":"grounded-answer-result-v1","citation_refs":["evidence-1"],"answer_chars":42}
```

字符数可以不同。不得把真实 key 写入 `.env`、命令历史、Compose 文件、测试 fixture、截图或提交的
日志。smoke 完成后，应在 DeepSeek 控制台撤销临时 key。

## 可选配置

- `-Model deepseek-v4-pro` 选择当前默认模型。
- `-BaseUrl https://api.deepseek.com` 选择官方 endpoint。

只有显式提供时，Compose 才会透传 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL` 和
`DEEPSEEK_BASE_URL`。应用默认路径仍保持 deterministic、offline-first 和低资源。如果当前 shell
中存在凭据，只能运行 `docker compose config --quiet`；普通的 `docker compose config` 会渲染
解析后的环境变量值，不得把其输出保存到日志。

本 smoke 只证明外部 Provider 兼容性，不证明真实 Memo 隐私验收、多实例运行、AgentRun 产品接入或
生产就绪。

DeepSeek 在 [模型与价格](https://api-docs.deepseek.com/quick_start/pricing/) 中说明
OpenAI-compatible base URL 和当前模型 ID。本 adapter 的固定请求设置遵循官方
[思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode) 与
[JSON Output](https://api-docs.deepseek.com/zh-cn/guides/json_mode/) 指南。
