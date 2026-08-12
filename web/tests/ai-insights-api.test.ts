import { afterEach, describe, expect, it, vi } from "vitest";
import { getAiMemoInsights, updateAiMemoInsightStatus } from "@/features/ai/api";

const insightResponse = {
  insight_id: "insight-1",
  memo_id: "memo-42",
  insight_type: "fact",
  title: "Port mapping",
  summary: "Use port 8080",
  confidence: 0.8,
  status: "pending",
  source_refs: ["summary"],
  version: 1,
  created_at: "2026-07-14T00:00:00+00:00",
  updated_at: "2026-07-14T00:00:00+00:00",
};

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("AI insight client", () => {
  it("reads reviewable insights for a Memo", async () => {
    vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000/");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([insightResponse]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAiMemoInsights("memo/42")).resolves.toEqual([insightResponse]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/ai/insights/memo%2F42",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("updates insight status with the current version", async () => {
    vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000");
    const accepted = { ...insightResponse, status: "accepted", version: 2 };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(accepted), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(updateAiMemoInsightStatus("memo-42", "insight-1", "accepted", 1)).resolves.toEqual(accepted);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/ai/insights/insight-1/status",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ memo_id: "memo-42", status: "accepted", version: 1 }),
      }),
    );
  });

  it("surfaces stale insight updates as an actionable error", async () => {
    vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 409 })));

    await expect(updateAiMemoInsightStatus("memo-42", "insight-1", "rejected", 1)).rejects.toThrow("stale");
  });
});
