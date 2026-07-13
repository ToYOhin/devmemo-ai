import { afterEach, describe, expect, it, vi } from "vitest";
import { getAiMemoNote, summarizeAiMemo } from "@/features/ai/api";

const noteResponse = {
  memo_id: "memo-42",
  summary: "Docker 容器端口映射问题分析",
  keywords: ["FastAPI", "Docker", "Network"],
  category: "DevOps",
  suggested_tags: ["docker", "network"],
  provider: "deterministic",
  created_at: "2026-07-13T00:00:00+00:00",
};

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("AI summary client", () => {
  it("reads a persisted note", async () => {
    vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000/");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(noteResponse), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAiMemoNote("memo/42")).resolves.toEqual(noteResponse);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/ai/notes/memo%2F42",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("treats a missing note as an ordinary Memo", async () => {
    vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 404 })));

    await expect(getAiMemoNote("missing")).resolves.toBeNull();
  });

  it("posts the current memo fields to generate a summary", async () => {
    vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(noteResponse), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const request = { memo_id: "memo-42", title: "Docker issue", content: "Port mapping failed", tags: ["Docker"] };

    await expect(summarizeAiMemo(request)).resolves.toEqual(noteResponse);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/ai/summarize",
      expect.objectContaining({
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(request),
      }),
    );
  });

  it("rejects invalid responses without exposing them to the UI", async () => {
    vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response("{}", { status: 200 }))
        .mockResolvedValueOnce(new Response("{}", { status: 200 })),
    );

    await expect(getAiMemoNote("invalid")).resolves.toBeNull();
    await expect(summarizeAiMemo({ memo_id: "invalid", title: "", content: "x", tags: [] })).rejects.toThrow(
      "AI summary response was invalid",
    );
  });
});
