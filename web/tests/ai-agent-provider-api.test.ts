import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth-state", () => ({
  getAccessToken: vi.fn(() => "test-access-token"),
}));

import {
  getAiAgentProviderSettings,
  parseAiAgentProviderSettings,
  testAiAgentProvider,
  updateAiAgentProviderSettings,
} from "@/features/ai/api";

const safeSettings = {
  version: "agent-provider-config-v1",
  provider: "openai",
  model: "gpt-4o-mini",
  base_url: "https://api.openai.com/v1",
  enabled: true,
  allow_real_memo_data: false,
  api_key_set: true,
  api_key_hint: "••••alue",
  config_version: 1,
  source: "stored",
} as const;

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Agent Provider BFF client", () => {
  it("reads only the masked settings projection", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(safeSettings), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAiAgentProviderSettings()).resolves.toEqual(safeSettings);
    expect(parseAiAgentProviderSettings({ ...safeSettings, api_key: "secret" })).toBeNull();
  });

  it("sends a write-only key through the same-origin admin route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(safeSettings), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const update = {
      version: "agent-provider-config-v1" as const,
      provider: "openai" as const,
      model: "gpt-4o-mini",
      base_url: "https://api.openai.com/v1",
      api_key: "synthetic-secret-value",
      enabled: true,
      allow_real_memo_data: false,
    };

    await expect(updateAiAgentProviderSettings(update)).resolves.toEqual(safeSettings);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/ai/agent/provider",
      expect.objectContaining({ method: "PUT", body: JSON.stringify(update) }),
    );
  });

  it("runs the explicit synthetic test route", async () => {
    const result = { status: "ok", provider: "openai", model: "gpt-4o-mini", latency_ms: 12 };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(testAiAgentProvider()).resolves.toEqual(result);
    expect(fetchMock).toHaveBeenCalledWith("/api/ai/agent/provider/test", expect.objectContaining({ method: "POST" }));
  });
});
