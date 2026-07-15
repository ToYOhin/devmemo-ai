import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { AiMemoInsight } from "@/features/ai/api";
import { type AiContextPackMemo, AiContextPackValidationError, buildContextPack } from "@/features/ai/contextPack";

const fixture = JSON.parse(readFileSync(resolve(process.cwd(), "../contracts/context-pack-v1.json"), "utf-8")) as {
  memos: Record<string, { memo_id: string; title: string; summary: string }>;
  insights: Record<string, AiMemoInsight>;
};
const memo: AiContextPackMemo = {
  memoId: fixture.memos["memo-bug"].memo_id,
  title: fixture.memos["memo-bug"].title,
  summary: fixture.memos["memo-bug"].summary,
};
const accepted = fixture.insights["insight-bug"];

const request = {
  question: "What should I know?",
  memoIds: [memo.memoId],
  insightIds: [accepted.insight_id],
  maxChars: 1000,
  maxItems: 10,
};

describe("Context Pack frontend contract", () => {
  it("builds bounded Markdown and JSON from explicit accepted inputs", () => {
    const response = buildContextPack(request, { [memo.memoId]: memo }, { [accepted.insight_id]: accepted });

    expect(response.packVersion).toBe("context-pack-v1");
    expect(response.markdown).toContain("insight-bug");
    expect(response.sources.map((source) => source.sourceId)).toEqual(["memo:memo-bug", "insight-bug"]);
    expect(JSON.parse(response.toJson()).items).toHaveLength(2);
    expect(response.toJson()).not.toContain("content");
  });

  it("does not implicitly include a Memo for an insight", () => {
    expect(() => buildContextPack({ ...request, memoIds: [] }, {}, { [accepted.insight_id]: accepted })).toThrow(AiContextPackValidationError);
  });

  it("excludes pending and rejected candidates through validation", () => {
    expect(() => buildContextPack(request, { [memo.memoId]: memo }, { [accepted.insight_id]: { ...accepted, status: "pending" } })).toThrow(/accepted/);
    expect(() => buildContextPack(request, { [memo.memoId]: memo }, { [accepted.insight_id]: { ...accepted, status: "rejected" } })).toThrow(/accepted/);
  });

  it("reports explicit truncation without exposing raw content", () => {
    const response = buildContextPack({ ...request, maxItems: 1, maxChars: 180 }, { [memo.memoId]: memo }, { [accepted.insight_id]: accepted });

    expect(response.items).toHaveLength(1);
    expect(response.truncated).toBe(true);
    expect(response.truncationReason).toBe("max_items");
    expect(response.markdown.length).toBeLessThanOrEqual(180);
    expect(response.markdown).not.toContain("raw content");
  });
});
