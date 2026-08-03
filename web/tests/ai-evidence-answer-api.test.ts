import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth-state", () => ({
  getAccessToken: vi.fn(() => "test-access-token"),
}));

import { parseAiEvidenceAnswer, requestAiEvidenceAnswer } from "@/features/ai/api";

const safeAnswer = {
  answer: "The port mapping is defined in the Compose file [1].",
  citations: [
    {
      memo_id: "memo-42",
      embedding_id: "memo-42",
      score: 0.9,
      title: "Docker ports",
      summary: "The Compose mapping is the source of the exposed port.",
      source_refs: ["title", "summary"],
      metadata: { memo_type: "memo", tags: ["docker"], index_version: "memo-v1" },
    },
  ],
  provider: "deterministic",
  retrieved_count: 1,
  agent_version: "evidence-answer-agent-v1",
  trace: {
    terminal_state: "answered",
    steps: [
      { index: 1, kind: "tool", name: "search_memos", status: "completed", result_count: 1 },
      { index: 2, kind: "final", name: "answer_from_evidence", status: "completed" },
    ],
  },
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Evidence Answer BFF client", () => {
  it("uses the same-origin BFF with only question and limit in the request body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(safeAnswer), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestAiEvidenceAnswer("Where is the port mapping?", 3)).resolves.toEqual({
      answer: safeAnswer.answer,
      citations: [
        {
          memo_id: "memo-42",
          title: "Docker ports",
          summary: "The Compose mapping is the source of the exposed port.",
          source_refs: ["title", "summary"],
        },
      ],
      trace: {
        terminal_state: "answered",
        steps: [
          { index: 1, name: "search_memos", status: "completed", result_count: 1 },
          { index: 2, name: "answer_from_evidence", status: "completed" },
        ],
      },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/ai/agent/answer",
      expect.objectContaining({
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          Authorization: "Bearer test-access-token",
        },
        body: JSON.stringify({ question: "Where is the port mapping?", limit: 3 }),
      }),
    );
  });

  it("rejects a response that attempts to extend the safe projection", () => {
    expect(parseAiEvidenceAnswer({ ...safeAnswer, content: "raw Memo content" })).toBeNull();
    expect(parseAiEvidenceAnswer({ ...safeAnswer, citations: [{ ...safeAnswer.citations[0], content: "raw Memo content" }] })).toBeNull();
  });

  it("accepts only the fixed refusal projection", () => {
    const refusal = {
      answer: "Request refused by the Agent safety policy.",
      citations: [],
      provider: "policy",
      retrieved_count: 0,
      agent_version: "evidence-answer-agent-v1",
      trace: {
        terminal_state: "refused",
        steps: [{ index: 1, kind: "final", name: "refuse_unsafe_request", status: "completed" }],
      },
    };

    expect(parseAiEvidenceAnswer(refusal)).toEqual({
      answer: refusal.answer,
      citations: [],
      trace: {
        terminal_state: "refused",
        steps: [{ index: 1, name: "refuse_unsafe_request", status: "completed" }],
      },
    });
    expect(parseAiEvidenceAnswer({ ...refusal, provider: "remote" })).toBeNull();
    expect(parseAiEvidenceAnswer({ ...refusal, answer: "untrusted refusal text" })).toBeNull();
    expect(
      parseAiEvidenceAnswer({
        ...safeAnswer,
        trace: { terminal_state: "no_context", steps: refusal.trace.steps },
      }),
    ).toBeNull();
  });
});
