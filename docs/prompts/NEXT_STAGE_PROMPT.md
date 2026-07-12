# 下一阶段 Prompt：Phase 2c Memos React 模板展示与复制 UI

将下面整段复制到新的 Codex 窗口或下一次任务中：

```text
你正在继续 H:\DevMemoAI 的 DevMemo AI 项目。

先读取以下真相源：
- docs/PROJECT_STATUS.md
- docs/HANDOFF.md
- docs/roadmap.md
- docs/structure.md
- docs/DOC_UPDATE_POLICY.md
- docs/DECISIONS.md
- docs/api.md
- git status --short --branch
- git log --oneline -8

当前已完成：
- AI Service 已解析并持久化 Code Snippet/Bug Report。
- memo_templates 按 memo_id 幂等 upsert，保存 payload 和 raw_content。
- GET /api/ai/templates/{memo_id} 已提供读取 API。
- AI Service 当前测试为 15 passed。

当前目标：在 Memos React 前端实现 Phase 2c 的最小模板展示/复制 UI。

本次只做一个可验证垂直切片：
1. 先定位现有 Memo 详情/展示组件、React Query/Connect 数据层和既有复制按钮模式。
2. 新增一个独立的 AI template client/hook，读取 AI Service 的 GET /api/ai/templates/{memo_id}。
3. 使用显式配置 `VITE_AI_SERVICE_URL`；未配置或请求失败时不影响 Memo 页面和普通 Markdown 展示。
4. Code Snippet 展示 title、language、description、tags、代码块和复制按钮。
5. Bug Report 展示 title、environment、error、reproduction_steps、root_cause、solution。
6. 复制按钮使用浏览器 Clipboard API，并提供失败/成功的可见反馈；不引入新的编辑器或高亮库，优先复用 Memos 现有 Markdown/highlight 能力。
7. 用 feature flag 或安全默认值控制新区域，默认 AI Service 不可用时隐藏/降级。

不要做：
- 不修改 Memos server/store/proto。
- 不加入 Qdrant、FastEmbed、RAG、AI chat。
- 不让 React 直接访问 SQLite。
- 不大范围重写 MemoEditor、React Query 或路由。
- 不为了 UI 引入 LangChain、LlamaIndex、CodeMirror 等新依赖。

实现要求：
- 遵循 AGENTS.md 的 React/TypeScript/Biome/React Query 约定。
- 组件、hook、API client 使用清晰的 AI feature 目录，避免散落到上游通用组件。
- 先写 API client/hook 测试或 mock，再接 UI；每一步先验证。
- 如果跨端口请求需要 CORS，只做最小配置，并记录决策，不修改 Memos 核心。

验证命令：
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- cd web; pnpm lint
- cd web; pnpm test
- cd web; pnpm build
- git diff --check

完成条件：
- Code Snippet 和 Bug Report UI 在有数据时可展示。
- 复制按钮有成功和失败反馈。
- AI Service 不可用、404、普通 Memo 时页面不报错、不影响原有内容。
- 新增 frontend tests；当前 AI Service 15 个测试仍全部通过。
- 更新 docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md。
- 更新本文件为下一阶段 Prompt，并同步 docs/prompts/NEW_WINDOW_PROMPT.md 的默认阶段描述。
- 如 API/结构/决策变化，同步 docs/api.md、docs/structure.md、docs/DECISIONS.md。
- 形成独立 commit，并报告真实验证结果和未验证项。

停止条件：
- 需要修改 Memos 核心 API 或数据库才能继续时，先停下并报告具体文件和影响。
- 前端依赖安装/构建因网络阻塞时，记录命令和证据，不把环境问题写成代码失败。
- 发现现有 UI 没有稳定的详情入口时，先做最小可访问的 memo detail surface，不自行扩大为完整 AI 助手页面。
```
