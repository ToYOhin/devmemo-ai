import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AiMemoContextPack from "@/features/ai/AiMemoContextPack";
import { useAiMemoInsights } from "@/features/ai/hooks";

vi.mock("@/features/ai/hooks", () => ({
  useAiMemoInsights: vi.fn(),
}));

vi.mock("@/utils/i18n", () => ({
  useTranslate: () => (key: string) =>
    ({
      "ai-context-pack.title": "Context Pack",
      "ai-context-pack.description": "Copy a bounded context.",
      "ai-context-pack.loading": "Loading",
      "ai-context-pack.load-failed": "Failed to load",
      "ai-context-pack.empty": "No accepted insights",
      "ai-context-pack.no-selection": "Select at least one source",
      "ai-context-pack.question": "Question",
      "ai-context-pack.default-question": "What should I know?",
      "ai-context-pack.max-chars": "Maximum characters",
      "ai-context-pack.max-items": "Maximum items",
      "ai-context-pack.sources": "Explicit sources",
      "ai-context-pack.explicit-selection": "Only checked sources are included.",
      "ai-context-pack.source-trace": "Sources in this pack",
      "ai-context-pack.truncated": "Pack truncated",
      "ai-context-pack.build-failed": "Build failed",
      "ai-context-pack.copy-markdown": "Copy Markdown",
      "ai-context-pack.copy-json": "Copy JSON",
      "ai-context-pack.copied": "Copied",
      "ai-context-pack.copy-failed": "Copy failed",
    })[key] ?? key,
}));

const useInsightsMock = vi.mocked(useAiMemoInsights);
const acceptedInsight = {
  insight_id: "insight-1",
  memo_id: "memo-1",
  insight_type: "fact" as const,
  title: "Accepted port fact",
  summary: "Use port 8080.",
  confidence: 0.9,
  status: "accepted" as const,
  source_refs: ["template.description"],
  version: 2,
  created_at: "2026-07-15T00:00:00+00:00",
  updated_at: "2026-07-15T00:00:00+00:00",
};

beforeEach(() => {
  vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000");
  useInsightsMock.mockReset();
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

describe("AI Memo Context Pack", () => {
  it("previews explicit accepted sources and copies Markdown/JSON", async () => {
    useInsightsMock.mockReturnValue({
      data: [
        acceptedInsight,
        { ...acceptedInsight, insight_id: "pending-1", title: "Pending secret", status: "pending" },
        { ...acceptedInsight, insight_id: "rejected-1", title: "Rejected secret", status: "rejected" },
      ],
      isError: false,
      isLoading: false,
    } as ReturnType<typeof useAiMemoInsights>);

    render(<AiMemoContextPack memoId="memo-1" memoTitle="Port mapping" />);

    expect(screen.getByTestId("ai-context-pack-panel")).toBeInTheDocument();
    expect(screen.getByTestId("ai-context-pack-preview")).toHaveTextContent("Accepted port fact");
    expect(screen.queryByText("Pending secret")).not.toBeInTheDocument();
    expect(screen.queryByText("Rejected secret")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Question" })).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "Maximum characters" })).toHaveValue(2000);
    expect(screen.getByRole("spinbutton", { name: "Maximum items" })).toHaveValue(8);
    expect(screen.getByText("Sources in this pack")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining("insight-1")));
    fireEvent.click(screen.getByRole("button", { name: "Copy JSON" }));
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringContaining('"packVersion":"context-pack-v1"')),
    );
  });

  it("supports explicit deselection and shows the empty state", () => {
    useInsightsMock.mockReturnValue({ data: [acceptedInsight], isError: false, isLoading: false } as ReturnType<typeof useAiMemoInsights>);
    const { unmount } = render(<AiMemoContextPack memoId="memo-1" memoTitle="Port mapping" />);

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[1]);
    expect(screen.getByTestId("ai-context-pack-preview")).not.toHaveTextContent("Accepted port fact");
    fireEvent.click(checkboxes[0]);
    expect(screen.getByTestId("ai-context-pack-empty")).toBeInTheDocument();

    unmount();
    useInsightsMock.mockReturnValue({ data: [], isError: false, isLoading: false } as ReturnType<typeof useAiMemoInsights>);
    render(<AiMemoContextPack memoId="memo-empty" memoTitle="Empty memo" />);
    expect(screen.getByTestId("ai-context-pack-empty")).toBeInTheDocument();
  });

  it("shows failure and clipboard error states without exposing content", async () => {
    useInsightsMock.mockReturnValue({ data: [], isError: true, isLoading: false } as ReturnType<typeof useAiMemoInsights>);
    render(<AiMemoContextPack memoId="memo-failed" memoTitle="Failed memo" />);
    expect(screen.getByTestId("ai-context-pack-error")).toBeInTheDocument();

    useInsightsMock.mockReturnValue({ data: [acceptedInsight], isError: false, isLoading: false } as ReturnType<typeof useAiMemoInsights>);
    const writeText = vi.fn().mockRejectedValue(new Error("clipboard unavailable"));
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<AiMemoContextPack memoId="memo-1" memoTitle="Port mapping" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));
    return waitFor(() => expect(screen.getByTestId("ai-context-pack-copy-error")).toBeInTheDocument());
  });
});
