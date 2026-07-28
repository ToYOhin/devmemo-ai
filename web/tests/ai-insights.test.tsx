import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AiMemoInsights from "@/features/ai/AiMemoInsights";
import { useAiMemoInsights, useUpdateAiMemoInsightStatus } from "@/features/ai/hooks";

vi.mock("@/features/ai/hooks", () => ({
  useAiMemoInsights: vi.fn(),
  useUpdateAiMemoInsightStatus: vi.fn(),
}));

vi.mock("@/utils/i18n", () => ({
  useTranslate: () => (key: string) =>
    ({
      "ai-insights.title": "AI Inbox",
      "ai-insights.review": "Reviewable memory",
      "ai-insights.sources": "Sources",
      "ai-insights.accept": "Accept",
      "ai-insights.reject": "Reject",
      "ai-insights.type-fact": "Fact",
      "ai-insights.status-pending": "Pending",
      "ai-insights.status-accepted": "Accepted",
      "ai-insights.status-rejected": "Rejected",
      "ai-insights.update-failed": "Failed to update insight",
      "ai-insights.load-failed": "Failed to load insights",
    })[key] ?? key,
}));

const useInsightsMock = vi.mocked(useAiMemoInsights);
const useUpdateMock = vi.mocked(useUpdateAiMemoInsightStatus);

beforeEach(() => {
  vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000");
  useInsightsMock.mockReset();
  useUpdateMock.mockReset();
});

describe("AI Memo Inbox", () => {
  it("renders a pending insight and allows explicit approval", () => {
    const mutate = vi.fn();
    useInsightsMock.mockReturnValue({
      data: [
        {
          insight_id: "insight-1",
          memo_id: "memo-1",
          insight_type: "fact",
          title: "Port mapping",
          summary: "Use port 8080",
          confidence: 0.8,
          status: "pending",
          source_refs: ["summary"],
          version: 1,
          created_at: "2026-07-14T00:00:00+00:00",
          updated_at: "2026-07-14T00:00:00+00:00",
        },
      ],
      isError: false,
    } as ReturnType<typeof useAiMemoInsights>);
    useUpdateMock.mockReturnValue({ mutate, isPending: false } as ReturnType<typeof useUpdateAiMemoInsightStatus>);

    render(<AiMemoInsights memoId="memo-1" />);

    expect(screen.getByTestId("ai-insights-panel")).toBeInTheDocument();
    expect(screen.getByText("Use port 8080")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(mutate).toHaveBeenCalledWith({ insightId: "insight-1", status: "accepted", version: 1 }, expect.anything());
  });

  it("stays hidden when there are no insights", () => {
    useInsightsMock.mockReturnValue({ data: [], isError: false } as ReturnType<typeof useAiMemoInsights>);
    useUpdateMock.mockReturnValue({ mutate: vi.fn(), isPending: false } as ReturnType<typeof useUpdateAiMemoInsightStatus>);

    render(<AiMemoInsights memoId="memo-empty" />);

    expect(screen.queryByTestId("ai-insights-panel")).not.toBeInTheDocument();
  });
});
