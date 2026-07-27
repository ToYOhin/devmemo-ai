# 下一阶段 Prompt：Phase 13 strict TypeScript lint gate promotion

~~~text
Phase 12 Web strict TypeScript baseline is complete. Independent `pnpm exec tsc --noEmit --pretty false` moved from 15 existing declaration errors to 0 without global `skipLibCheck`, disabled strictness, broad `any`, `@ts-ignore`, dependency changes, or lockfile changes. The solution uses an explicit project callback type, two exact TypeScript-only paths for TanStack Query Devtools/goober, and narrow declarations for Mermaid/type-fest and React Leaflet/MarkerCluster. Targeted tests are 2/2, full Web tests are 33 files / 149 passed, and build, project lint, Compose config, and diff check pass. Read `docs/handoffs/2026-07-27-web-strict-typescript-handoff.md`. Keep `AI_PUBLIC_CHUNK_RETRIEVAL=false`.

继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，也不要并行修改 project4 下的其他 worktree。整体推进一个完整、可验证的阶段切片；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-27-web-strict-typescript-handoff.md
2. docs/PROJECT_STATUS.md 顶部
3. docs/HANDOFF.md 顶部
4. docs/roadmap.md 的 Phase 12/13
5. docs/DECISIONS.md 的 ADR-051
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 12 的独立 strict TypeScript 已为 0 errors。兼容层只影响 TypeScript 类型解析；production build 继续使用已安装 package 的运行时代码。
- `web/package.json` 的项目 lint 仍使用 `tsc --noEmit --skipLibCheck && biome check src`，所以日常/CI 风格门禁尚未强制执行已经通过的 strict baseline。
- package 与 lockfile 在 Phase 12 未改变；TanStack Query Devtools、goober、Mermaid/type-fest、React Leaflet/MarkerCluster 的 bridge 均为窄范围声明，不应在没有上游替代证据时扩大或删除。
- Phase 10 route B 已完成，不再重复；Phase 11 的真实详情页/系统剪贴板复核因当前 Chrome profile 无有效 Memos 登录态而未验证，不能写成 pass。
- 默认保持 deterministic + memory、`AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、`AI_VECTOR_STORE=memory`、`AI_PUBLIC_CHUNK_RETRIEVAL=false`。

本阶段唯一目标：Phase 13 把 Web 项目 lint 的 TypeScript 子门禁提升到 strict baseline，使 `pnpm lint` 直接执行不带 `--skipLibCheck` 的 `tsc --noEmit`，并保持运行时行为与公共契约不变。

执行边界：
- 先分别运行 `pnpm exec tsc --noEmit --pretty false` 与当前 `pnpm lint`，确认 Phase 12 基线仍通过。
- 只把 `web/package.json` 的 lint script 从 `tsc --noEmit --skipLibCheck && biome check src` 改为 `tsc --noEmit && biome check src`；不修改 TypeScript strict 配置，不新增其他 script 或 suppression。
- 本切片不新增、升级或删除依赖，不改 lockfile，不扩大或重写 Phase 12 declaration bridge。若移除 flag 后出现与独立 strict 命令不同的错误，停止在准确诊断，不用新的 paths、`any`、`@ts-ignore` 或局部 skip 掩盖。
- 不修改 Context Pack contract/golden、Memos server/store/proto、AI Service API、`/api/ai/chat`、CitationResponse、memo-v1、public-chunk contract、collection 或 volume。
- 不创建/修改/删除 Memo 或 Insight，不提取 token，不绕过 Memos 认证，不启动 Chrome/Qdrant/Ollama，不重跑 Phase 10 route B。

验证顺序：
1. `pnpm lint`，确认 strict tsc 与 Biome 一起通过。
2. `pnpm exec tsc --noEmit --pretty false`，确认显式 strict 命令仍为 0。
3. 串行运行 `pnpm exec vitest run --maxWorkers=1` 与 `pnpm build`。
4. `docker compose config --quiet`；没有后端代码改动，不重跑 AI Service 全量或 `verify-devmemo.ps1`。
5. `git diff --check`。

完成后更新 PROJECT_STATUS、CHANGELOG_AI、HANDOFF、roadmap、structure、DECISIONS、新 handoff 和本 Prompt；形成独立 commit，不自动 push。若门禁提升出现无法在既有 Phase 12 边界内解释的差异，只提交准确诊断/提案，不伪造通过。
~~~
