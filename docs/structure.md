# 项目结构与边界

## 当前结构

```text
H:/DevMemoAI
├── cmd/ server/ store/ proto/ web/     # Memos upstream 区
├── ai-service/                         # 独立 Python AI 服务
│   ├── main.py                         # 稳定启动入口
│   ├── app/domain/models.py            # CodeSnippet/BugReport/ParsedMemo
│   ├── app/services/content_parser.py # Markdown/frontmatter parser
│   ├── llm.py / database.py            # MVP 适配器与 ai_notes/memo_templates 持久化
│   ├── embedding.py / rag.py           # Phase 3 边界接口
│   └── tests/                          # AI Service 测试
├── integrations/memos/                 # Memos 接入说明
├── docs/                               # 架构、路线、API、采用记录
├── scripts/                            # Windows 开发与验证脚本
└── docker-compose.yml                  # 本地完整环境入口
```

## 目标结构

```text
ai-service/
├── app/
│   ├── api/                            # FastAPI routes + request mapping
│   ├── domain/                         # provider-neutral models
│   ├── services/                       # summarize/index/answer use cases
│   ├── adapters/
│   │   ├── llm/                        # deterministic/openai/ollama
│   │   ├── embedding/                  # fastembed/remote/fake
│   │   ├── vectorstore/                # qdrant adapter
│   │   └── persistence/                # sqlite, later postgres if needed
│   └── settings.py                     # environment-only configuration
├── migrations/                         # AI-owned schema/index migrations
├── tests/{unit,contract,integration}/
└── main.py                             # compatibility launcher
```

## 迁移规则

1. 先新增 `app/` 模块和测试，再把旧平面模块改为兼容导出。
2. 每次只迁移一个边界：domain -> services -> adapters -> routes。
3. `uvicorn main:app --app-dir ai-service` 和现有测试命令必须保持可用。
4. 不把 qdrant-client、fastembed、httpx 类型放入 domain。

Memos 负责 Memo、搜索、标签、权限和原始 Markdown；AI Service 负责派生摘要、关键词、embedding 和回答。现阶段通过用户 Webhook 集成，后续优先增加 outbox/重试，不直接修改 Memos Store。
