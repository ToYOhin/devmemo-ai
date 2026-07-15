import { describe, expect, it } from "vitest";
import type { AiMemoInsight } from "@/features/ai/api";
import { type AiContextPackMemo, AiContextPackValidationError, buildContextPack } from "@/features/ai/contextPack";

const memo: AiContextPackMemo = { memoId: "memo-1", title: "Port mapping", summary: "Use the host port." };
const accepted: AiMemoInsight = {
  insight_id: "insight-1",
  memo_id: "memo-1",
  insight_type: "fact",
  title: "Use port 8080",
  summary: "The service listens on port 8080.",
  confidence: 0.9,
  status: "accepted",
  source_refs: ["template.description"],
  version: 2,
  created_at: "2026-07-15T00:00:00+00:00",
  updated_at: "2026-07-15T00:00:00+00:00",
};

const request = { question: "What should I know?", memoIds: ["memo-1"], insightIds: ["insight-1"], maxChars: 1000, maxItems: 10 };

describe("Context Pack frontend contract", () => {
  it("builds bounded Markdown and JSON from explicit accepted inputs", () => {
    const response = buildContextPack(request, { "memo-1": memo }, { "insight-1": accepted });

    expect(response.packVersion).toBe("context-pack-v1");
    expect(response.markdown).toContain("insight-1");
    expect(response.sources.map((source) => source.sourceId)).toEqual(["memo:memo-1", "insight-1"]);
    expect(JSON.parse(response.toJson()).items).toHaveLength(2);
    expect(response.toJson()).not.toContain("content");
  });

  it("does not implicitly include a Memo for an insight", () => {
    expect(() => buildContextPack({ ...request, memoIds: [] }, {}, { "insight-1": accepted })).toThrow(AiContextPackValidationError);
  });

  it("excludes pending and rejected candidates through validation", () => {
    expect(() => buildContextPack(request, { "memo-1": memo }, { "insight-1": { ...accepted, status: "pending" } })).toThrow(/accepted/);
    expect(() => buildContextPack(request, { "memo-1": memo }, { "insight-1": { ...accepted, status: "rejected" } })).toThrow(/accepted/);
  });

  it("reports explicit truncation without exposing raw content", () => {
    const response = buildContextPack({ ...request, maxItems: 1, maxChars: 180 }, { "memo-1": memo }, { "insight-1": accepted });

    expect(response.items).toHaveLength(1);
    expect(response.truncated).toBe(true);
    expect(response.truncationReason).toBe("max_items");
    expect(response.markdown.length).toBeLessThanOrEqual(180);
    expect(response.markdown).not.toContain("raw content");
  });
});
