import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AiMemoSummary from "@/features/ai/AiMemoSummary";
import { useAiMemoNote, useGenerateAiMemoSummary } from "@/features/ai/hooks";

vi.mock("@/features/ai/hooks", () => ({
  useAiMemoNote: vi.fn(),
  useGenerateAiMemoSummary: vi.fn(),
}));

vi.mock("@/utils/i18n", () => ({
  useTranslate: () => (key: string) =>
    ({
      "ai-summary.title": "AI Summary",
      "ai-summary.summary": "Summary",
      "ai-summary.keywords": "Keywords",
      "ai-summary.category": "Category",
      "ai-summary.generate": "Generate summary",
      "ai-summary.regenerate": "Regenerate summary",
      "ai-summary.generating": "Generating...",
      "ai-summary.generated": "Summary generated",
      "ai-summary.generate-failed": "Failed to generate summary",
    })[key] ?? key,
}));

vi.mock("react-hot-toast", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const useAiMemoNoteMock = vi.mocked(useAiMemoNote);
const useGenerateAiMemoSummaryMock = vi.mocked(useGenerateAiMemoSummary);

const note = {
  memo_id: "memo-42",
  summary: "Docker 容器端口映射问题分析",
  keywords: ["Docker", "Network"],
  category: "DevOps",
  suggested_tags: ["docker"],
  provider: "deterministic",
  created_at: "2026-07-13T00:00:00+00:00",
};

beforeEach(() => {
  vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000");
  useAiMemoNoteMock.mockReturnValue({ data: note } as ReturnType<typeof useAiMemoNote>);
  useGenerateAiMemoSummaryMock.mockReturnValue({
    isPending: false,
    mutate: vi.fn(),
  } as unknown as ReturnType<typeof useGenerateAiMemoSummary>);
});

describe("AI Memo summary panel", () => {
  it("shows persisted summary fields and regenerates with primitive Memo data", () => {
    const mutate = vi.fn();
    useGenerateAiMemoSummaryMock.mockReturnValue({
      isPending: false,
      mutate,
    } as unknown as ReturnType<typeof useGenerateAiMemoSummary>);

    render(<AiMemoSummary memoId="memo-42" title="Docker issue" content="Port mapping failed" tags={["Docker"]} />);

    expect(screen.getByTestId("ai-summary-panel")).toBeInTheDocument();
    expect(screen.getByText("Docker 容器端口映射问题分析")).toBeInTheDocument();
    expect(screen.getByText("Network")).toBeInTheDocument();
    expect(screen.getByText("DevOps")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Regenerate summary" }));

    expect(mutate).toHaveBeenCalledWith(
      { memo_id: "memo-42", title: "Docker issue", content: "Port mapping failed", tags: ["Docker"] },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });

  it("shows only a generate action when no summary exists", () => {
    useAiMemoNoteMock.mockReturnValue({ data: null } as ReturnType<typeof useAiMemoNote>);

    render(<AiMemoSummary memoId="memo-plain" title="Plain memo" content="Some content" tags={[]} />);

    expect(screen.getByTestId("ai-summary-action")).toBeInTheDocument();
    expect(screen.queryByTestId("ai-summary-panel")).not.toBeInTheDocument();
  });

  it("shows visible feedback when generation fails", () => {
    const mutate = vi.fn((_request, callbacks) => callbacks?.onError?.(new Error("offline")));
    useAiMemoNoteMock.mockReturnValue({ data: null } as ReturnType<typeof useAiMemoNote>);
    useGenerateAiMemoSummaryMock.mockReturnValue({
      isPending: false,
      mutate,
    } as unknown as ReturnType<typeof useGenerateAiMemoSummary>);

    render(<AiMemoSummary memoId="memo-offline" title="Offline" content="Some content" tags={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Generate summary" }));

    expect(screen.getByTestId("ai-summary-feedback")).toHaveTextContent("Failed to generate summary");
  });
});
