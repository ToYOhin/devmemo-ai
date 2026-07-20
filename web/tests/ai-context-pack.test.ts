import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { AiMemoInsight } from "@/features/ai/api";
import { type AiContextPackMemo, AiContextPackValidationError, buildContextPack } from "@/features/ai/contextPack";

const fixture = JSON.parse(readFileSync(resolve(process.cwd(), "../contracts/context-pack-v1.json"), "utf-8")) as {
  memos: Record<string, { memo_id: string; title: string; summary: string }>;
  insights: Record<string, AiMemoInsight>;
  golden_cases: Record<
    string,
    {
      request: { question: string; memo_ids: string[]; insight_ids: string[]; max_chars: number; max_items: number };
      expected: { markdown: string; json: Record<string, unknown> };
    }
  >;
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

  it.each(Object.entries(fixture.golden_cases))("matches the shared %s Markdown and canonical JSON golden output", (_name, goldenCase) => {
    const response = buildContextPack(
      {
        question: goldenCase.request.question,
        memoIds: goldenCase.request.memo_ids,
        insightIds: goldenCase.request.insight_ids,
        maxChars: goldenCase.request.max_chars,
        maxItems: goldenCase.request.max_items,
      },
      Object.fromEntries(
        Object.entries(fixture.memos).map(([memoId, value]) => [memoId, { memoId: value.memo_id, title: value.title, summary: value.summary }]),
      ),
      fixture.insights,
    );

    expect(response.markdown).toBe(goldenCase.expected.markdown);
    expect(response.toJson()).toBe(JSON.stringify(goldenCase.expected.json));
    expect(response.toJson()).not.toContain("Pending fact");
  });
});
