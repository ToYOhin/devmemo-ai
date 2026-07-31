import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AiMemoEvidenceAnswer from "@/features/ai/AiMemoEvidenceAnswer";

vi.mock("@/utils/i18n", () => ({
  useTranslate: () => (key: string, values?: { count?: number }) =>
    ({
      "ai-evidence-answer.title": "Evidence Answer",
      "ai-evidence-answer.description": "Experimental and read-only.",
      "ai-evidence-answer.experimental": "Experimental",
      "ai-evidence-answer.start": "Ask Evidence Agent",
      "ai-evidence-answer.question": "Question",
      "ai-evidence-answer.question-placeholder": "Ask a question",
      "ai-evidence-answer.limit": "Maximum citations",
      "ai-evidence-answer.submit": "Answer from evidence",
      "ai-evidence-answer.submitting": "Searching Memos...",
      "ai-evidence-answer.answer": "Answer",
      "ai-evidence-answer.citations": "Citations",
      "ai-evidence-answer.citation-source-refs": "Safe source fields",
      "ai-evidence-answer.no-citations": "No matching indexed Memo was found.",
      "ai-evidence-answer.trace": "Execution trace",
      "ai-evidence-answer.trace-search_memos": "Search Memos",
      "ai-evidence-answer.trace-answer_from_evidence": "Answer from evidence",
      "ai-evidence-answer.trace-results_one": `${values?.count} result`,
      "ai-evidence-answer.trace-results_other": `${values?.count} results`,
      "ai-evidence-answer.error-invalid": "Enter a valid question and limit.",
      "ai-evidence-answer.error-unavailable": "Evidence Answer is not enabled.",
      "ai-evidence-answer.error-auth": "Sign in again.",
      "ai-evidence-answer.error-failed": "Evidence Answer is temporarily unavailable.",
    })[key] ?? key,
}));

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

describe("Evidence Answer entry", () => {
  it("requires an explicit opt-in and renders only the safe BFF projection", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(safeAnswer), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<AiMemoEvidenceAnswer />);

    expect(screen.getByTestId("ai-evidence-answer-panel")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask Evidence Agent" })).toHaveAttribute("aria-expanded", "false");
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Ask Evidence Agent" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Question" }), { target: { value: "Where is the port mapping?" } });
    fireEvent.click(screen.getByRole("button", { name: "Answer from evidence" }));

    await waitFor(() => expect(screen.getByTestId("ai-evidence-answer-result")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/ai/agent/answer",
      expect.objectContaining({ body: JSON.stringify({ question: "Where is the port mapping?", limit: 5 }) }),
    );
    expect(screen.getByText("The port mapping is defined in the Compose file [1].")).toBeInTheDocument();
    expect(screen.getByText("Docker ports")).toBeInTheDocument();
    expect(screen.getByText(/Search Memos/)).toBeInTheDocument();
    expect(screen.queryByText("deterministic")).not.toBeInTheDocument();
    expect(screen.queryByText("memo-v1")).not.toBeInTheDocument();
    expect(screen.queryByText("memo-42")).not.toBeInTheDocument();
  });

  it("does not issue a request for an invalid explicit submission", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<AiMemoEvidenceAnswer />);
    fireEvent.click(screen.getByRole("button", { name: "Ask Evidence Agent" }));
    fireEvent.click(screen.getByRole("button", { name: "Answer from evidence" }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("ai-evidence-answer-error")).toHaveTextContent("Enter a valid question and limit.");
  });
});
