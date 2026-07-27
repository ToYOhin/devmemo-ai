# DevMemo AI Phase 12 Web strict TypeScript 交接

更新时间：2026-07-27

## 完成结论

Phase 12 已完成。`web/` 的独立 `pnpm exec tsc --noEmit --pretty false` 从 15 个既有声明错误收敛到 0，未降低 strict、未启用全局 `skipLibCheck`、未使用宽泛 `any`/`@ts-ignore`，也未新增或升级依赖。工作仅发生在 `H:\DevMemoAI` 主工作树，未启动并行 Agent 或其他 worktree。

## 根因与修复

| 基线类别 | 数量 | 修复 |
| --- | ---: | --- |
| TanStack Query Devtools / Solid | 6 | 为 React wrapper 实际消费的 button position、panel position、theme 与 error type 建立精确 TypeScript path |
| goober ESM declaration | 1 | 为 react-hot-toast 实际消费的 `DefaultTheme`/`StyledVNode` 建立精确 TypeScript path |
| Mermaid / type-fest | 1 | 本地声明 `SetOptional`/`SetRequired` 的准确 utility 语义 |
| Leaflet MarkerCluster | 2 | 以 Leaflet module augmentation 补齐当前组件需要的 options 与 group/cluster 类型 |
| React Leaflet deep context | 4 | 声明 package 已发布但未从 exports 暴露的 `ControlledLayer` type path |
| 项目 `FunctionType` | 1 | `DialogCallback.destroy` 改用明确的 `() => void`，并移除与 `common.ts` 同名而未进入编译的无效声明文件 |

`web/tsconfig.json` 新增的两个 paths 只影响 TypeScript 类型解析。Vite production build 已证明运行时代码仍从安装的 package 解析；package.json 与 lockfile 未改变。

## 验证

在所有源码与类型改动完成后按低并发顺序执行：

- `pnpm exec tsc --noEmit --pretty false`：通过，0 errors。
- `pnpm exec vitest run tests/mermaid-block.test.tsx tests/location-picker.test.tsx --maxWorkers=1`：`2 files / 2 passed`。
- `pnpm exec vitest run --maxWorkers=1`：`33 files / 149 passed`。
- `pnpm build`：通过；保留既有大 chunk 与 plugin timing 警告。
- `pnpm lint`：通过。
- `docker compose config --quiet`：通过。
- `git diff --check`：通过。

没有后端运行时代码改动，因此没有重跑 AI Service 全量测试或 `scripts/verify-devmemo.ps1`。没有启动 Chrome、Qdrant 或 Ollama。

## 保持不变

- Memos Go server/store/proto 仍是 Memo 与权限事实源。
- AI Service、SQLite、Webhook、Context Pack contract/golden、公共 `/api/ai/chat` 与 CitationResponse 均未修改。
- 默认仍为 deterministic + memory、`AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、`AI_VECTOR_STORE=memory`。
- `AI_PUBLIC_CHUNK_RETRIEVAL=false`；没有 gateway rollout、浏览器签名、collection 或 volume 变化。
- Phase 10 route B 没有重跑；Phase 11 的真实详情页/系统剪贴板复核仍是认证会话缺失下的未验证状态。

## 下一阶段

执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 13：把 `pnpm lint` 内的 TypeScript 子门禁从 `tsc --noEmit --skipLibCheck` 提升为 `tsc --noEmit`，让已经通过的 strict baseline 成为项目日常门禁。只允许门禁、验证与文档变化；不升级依赖、不扩大声明 bridge、不改变运行时行为。完成后独立提交，不自动 push。
