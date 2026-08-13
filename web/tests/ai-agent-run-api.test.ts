import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth-state", () => ({
  getAccessToken: vi.fn(() => "test-access-token"),
}));

import { parseAiAgentRunArtifact, parseAiAgentRunStatus, requestAiAgentRun, requestAiAgentRunArtifact } from "@/features/ai/api";

const safeStatus = {
  run_id: "run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  status: "succeeded",
  created_at: "2026-08-13T08:00:00Z",
  updated_at: "2026-08-13T08:00:01Z",
  last_event_seq: 6,
  source_count: 1,
  terminal_reason: null,
  artifact_id: "artifact-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
};

const safeArtifact = {
  artifact_id: "artifact-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  file_name: "project-summary.md",
  media_type: "text/markdown",
  markdown: "# Project summary\n",
  digest: "a".repeat(64),
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AgentRun BFF client", () => {
  it("creates a preset run through the same-origin BFF", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(safeStatus), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestAiAgentRun("project_summary", "request-1", ["memo-42"])).resolves.toEqual(safeStatus);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/ai/agent/runs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ task_kind: "project_summary", request_key: "request-1", memo_uids: ["memo-42"] }),
      }),
    );
  });

  it("reads only the strict Markdown artifact projection", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(safeArtifact), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestAiAgentRunArtifact(safeStatus.run_id)).resolves.toEqual(safeArtifact);
    expect(fetchMock).toHaveBeenCalledWith(`/api/ai/agent/runs/${safeStatus.run_id}/artifact`, expect.any(Object));
    expect(parseAiAgentRunArtifact({ ...safeArtifact, subject_id: "user-17" })).toBeNull();
  });

  it("rejects uncontracted status fields", () => {
    expect(parseAiAgentRunStatus(safeStatus)).toEqual(safeStatus);
    expect(parseAiAgentRunStatus({ ...safeStatus, source_snapshot: [] })).toBeNull();
    expect(parseAiAgentRunStatus({ ...safeStatus, status: "expired" })).toBeNull();
  });
});
