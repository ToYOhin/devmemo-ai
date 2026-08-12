import { afterEach, describe, expect, it, vi } from "vitest";
import { getAiMemoTemplate } from "@/features/ai/api";

const templateResponse = {
  memo_id: "memo-42",
  kind: "code",
  payload: {
    title: "Port check",
    language: "Go",
    code: "fmt.Println(8080)",
    description: "Check the port.",
    tags: ["Docker"],
  },
  raw_content: "type: code",
  created_at: "2026-07-12T00:00:00+00:00",
  updated_at: "2026-07-12T00:00:00+00:00",
};

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("AI template client", () => {
  it("reads a template through the same-origin BFF", async () => {
    vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000/");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(templateResponse), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAiMemoTemplate("memo/code 42")).resolves.toEqual(templateResponse);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/ai/templates/memo%2Fcode%2042",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("treats a missing template as an ordinary Memo", async () => {
    vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 404 })));

    await expect(getAiMemoTemplate("missing")).resolves.toBeNull();
  });

  it("does not request the service when it is not configured", async () => {
    vi.stubEnv("VITE_AI_SERVICE_URL", "");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAiMemoTemplate("memo-plain")).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
