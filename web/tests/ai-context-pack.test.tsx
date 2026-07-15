import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AiMemoContextPack from "@/features/ai/AiMemoContextPack";
import { useAiMemoInsightsForMemos } from "@/features/ai/hooks";
import { useInfiniteMemos } from "@/hooks/useMemoQueries";

vi.mock("@/features/ai/hooks", () => ({
  useAiMemoInsightsForMemos: vi.fn(),
}));

vi.mock("@/hooks/useMemoQueries", () => ({
  useInfiniteMemos: vi.fn(),
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
      "ai-context-pack.memo-source": "Memo source",
      "ai-context-pack.insight-source": "Insight source",
      "ai-context-pack.insights-unavailable": "Some selected Memo insights are unavailable and were excluded.",
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

const useInsightsMock = vi.mocked(useAiMemoInsightsForMemos);
const useMemosMock = vi.mocked(useInfiniteMemos);
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
  useMemosMock.mockReset();
  useMemosMock.mockReturnValue({ data: { pages: [{ memos: [] }] }, isError: false, isLoading: false } as ReturnType<typeof useInfiniteMemos>);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

describe("AI Memo Context Pack", () => {
  it("previews explicit accepted sources and copies Markdown/JSON", async () => {
    useInsightsMock.mockReturnValue([{ data: [
        acceptedInsight,
        { ...acceptedInsight, insight_id: "pending-1", title: "Pending secret", status: "pending" },
        { ...acceptedInsight, insight_id: "rejected-1", title: "Rejected secret", status: "rejected" },
      ],
      isError: false,
      isLoading: false,
    }] as ReturnType<typeof useAiMemoInsightsForMemos>);

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
    useInsightsMock.mockReturnValue([{ data: [acceptedInsight], isError: false, isLoading: false }] as ReturnType<typeof useAiMemoInsightsForMemos>);
    const { unmount } = render(<AiMemoContextPack memoId="memo-1" memoTitle="Port mapping" />);

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[1]);
    expect(screen.getByTestId("ai-context-pack-preview")).not.toHaveTextContent("Accepted port fact");
    fireEvent.click(checkboxes[0]);
    expect(screen.getByTestId("ai-context-pack-empty")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Memo source Port mapping" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Memo source Port mapping" }));
    expect(screen.getByTestId("ai-context-pack-preview")).toHaveTextContent("Accepted port fact");

    unmount();
    useInsightsMock.mockReturnValue([{ data: [], isError: false, isLoading: false }] as ReturnType<typeof useAiMemoInsightsForMemos>);
    render(<AiMemoContextPack memoId="memo-empty" memoTitle="Empty memo" />);
    expect(screen.getByTestId("ai-context-pack-empty")).toBeInTheDocument();
  });

  it("shows failure and clipboard error states without exposing content", async () => {
    useInsightsMock.mockReturnValue([{ data: [], isError: true, isLoading: false }] as ReturnType<typeof useAiMemoInsightsForMemos>);
    render(<AiMemoContextPack memoId="memo-failed" memoTitle="Failed memo" />);
    expect(screen.getByTestId("ai-context-pack-error")).toBeInTheDocument();

    useInsightsMock.mockReturnValue([{ data: [acceptedInsight], isError: false, isLoading: false }] as ReturnType<typeof useAiMemoInsightsForMemos>);
    const writeText = vi.fn().mockRejectedValue(new Error("clipboard unavailable"));
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<AiMemoContextPack memoId="memo-1" memoTitle="Port mapping" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));
    return waitFor(() => expect(screen.getByTestId("ai-context-pack-copy-error")).toBeInTheDocument());
  });

  it("falls back to the legacy DOM copy path when clipboard permission is unavailable", async () => {
    useInsightsMock.mockReturnValue([{ data: [acceptedInsight], isError: false, isLoading: false }] as ReturnType<typeof useAiMemoInsightsForMemos>);
    const writeText = vi.fn().mockRejectedValue(new Error("clipboard permission denied"));
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, "execCommand", { configurable: true, value: execCommand });

    render(<AiMemoContextPack memoId="memo-1" memoTitle="Port mapping" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));

    await waitFor(() => expect(execCommand).toHaveBeenCalledWith("copy"));
    expect(screen.queryByTestId("ai-context-pack-copy-error")).not.toBeInTheDocument();
    delete (document as Document & { execCommand?: unknown }).execCommand;
  });

  it("allows only explicitly checked visible Memos and removes a revoked source", async () => {
    const crossInsight = { ...acceptedInsight, insight_id: "insight-2", memo_id: "memo-2", title: "Cross Memo action" };
    useMemosMock.mockReturnValue({
      data: { pages: [{ memos: [{ name: "memos/memo-1", property: { title: "Port mapping" } }, { name: "memos/memo-2", property: { title: "Second memo" } }] }] },
      isError: false,
      isLoading: false,
    } as ReturnType<typeof useInfiniteMemos>);
    useInsightsMock.mockImplementation((memoIds) =>
      memoIds.map((memoId) => ({
        data: memoId === "memo-2" ? [crossInsight] : [acceptedInsight],
        isError: false,
        isLoading: false,
      })) as ReturnType<typeof useAiMemoInsightsForMemos>,
    );

    render(<AiMemoContextPack memoId="memo-1" memoTitle="Port mapping" />);

    const crossMemoCheckbox = screen.getByRole("checkbox", { name: "Memo source Second memo" });
    expect(crossMemoCheckbox).not.toBeChecked();
    expect(screen.getByTestId("ai-context-pack-preview")).not.toHaveTextContent("Second memo");
    fireEvent.click(crossMemoCheckbox);
    await waitFor(() => expect(screen.getByTestId("ai-context-pack-preview")).toHaveTextContent("Second memo"));
    expect(screen.getByTestId("ai-context-pack-preview")).toHaveTextContent("Cross Memo action");

    fireEvent.click(crossMemoCheckbox);
    await waitFor(() => expect(screen.getByTestId("ai-context-pack-preview")).not.toHaveTextContent("Cross Memo action"));
  });

  it("excludes an additional Memo when its permission-scoped insight query becomes unavailable", async () => {
    let crossMemoAvailable = true;
    const crossInsight = { ...acceptedInsight, insight_id: "insight-2", memo_id: "memo-2", title: "Private cross action" };
    useMemosMock.mockReturnValue({
      data: { pages: [{ memos: [{ name: "memo-2", property: { title: "Private memo" } }] }] },
      isError: false,
      isLoading: false,
    } as ReturnType<typeof useInfiniteMemos>);
    useInsightsMock.mockImplementation((memoIds) =>
      memoIds.map((memoId) => ({
        data: memoId === "memo-2" && crossMemoAvailable ? [crossInsight] : memoId === "memo-2" ? [] : [acceptedInsight],
        isError: memoId === "memo-2" && !crossMemoAvailable,
        isLoading: false,
      })) as ReturnType<typeof useAiMemoInsightsForMemos>,
    );

    const { rerender } = render(<AiMemoContextPack memoId="memo-1" memoTitle="Port mapping" />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Memo source Private memo" }));
    await waitFor(() => expect(screen.getByTestId("ai-context-pack-preview")).toHaveTextContent("Private memo"));

    crossMemoAvailable = false;
    rerender(<AiMemoContextPack memoId="memo-1" memoTitle="Port mapping" />);
    await waitFor(() => expect(screen.getByTestId("ai-context-pack-unavailable")).toBeInTheDocument());
    expect(screen.getByTestId("ai-context-pack-preview")).not.toHaveTextContent("Private memo");
    expect(screen.getByTestId("ai-context-pack-preview")).not.toHaveTextContent("Private cross action");
  });
});
