import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AiMemoTemplate from "@/features/ai/AiMemoTemplate";
import { useAiMemoTemplate } from "@/features/ai/hooks";

vi.mock("@/features/ai/hooks", () => ({
  useAiMemoTemplate: vi.fn(),
}));

vi.mock("@/utils/i18n", () => ({
  useTranslate: () => (key: string) =>
    ({
      "ai-template.title": "AI Template",
      "ai-template.code-snippet": "Code Snippet",
      "ai-template.bug-report": "Bug Report",
      "ai-template.environment": "Environment",
      "ai-template.error": "Error",
      "ai-template.reproduction-steps": "Reproduction steps",
      "ai-template.root-cause": "Root cause",
      "ai-template.solution": "Solution",
      "ai-template.copy": "Copy code",
      "ai-template.copied": "Copied",
      "ai-template.copy-failed": "Copy failed",
      "common.title": "Title",
      "common.language": "Language",
      "common.description": "Description",
    })[key] ?? key,
}));

const useAiMemoTemplateMock = vi.mocked(useAiMemoTemplate);

const codeTemplate = {
  memo_id: "memo-code",
  kind: "code" as const,
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

const bugTemplate = {
  memo_id: "memo-bug",
  kind: "bug" as const,
  payload: {
    title: "FastAPI startup failure",
    environment: "Python 3.12 / Ubuntu 22",
    error: "ModuleNotFoundError",
    reproduction_steps: "Run uvicorn main:app",
    root_cause: "Dependency was missing",
    solution: "Install the requirements",
    tags: [],
  },
  raw_content: "type: bug",
  created_at: "2026-07-12T00:00:00+00:00",
  updated_at: "2026-07-12T00:00:00+00:00",
};

beforeEach(() => {
  vi.stubEnv("VITE_AI_SERVICE_URL", "http://localhost:8000");
  useAiMemoTemplateMock.mockReset();
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

describe("AI Memo template panel", () => {
  it("renders a Code Snippet and reports copy success", async () => {
    useAiMemoTemplateMock.mockReturnValue({ data: codeTemplate } as ReturnType<typeof useAiMemoTemplate>);

    render(<AiMemoTemplate memoId="memo-code" />);

    expect(screen.getByTestId("ai-template-panel")).toBeInTheDocument();
    expect(screen.getByText("Port check")).toBeInTheDocument();
    const codeBlock = screen.getByTestId("ai-template-panel").querySelector("code");
    expect(codeBlock).not.toBeNull();
    expect(codeBlock).toHaveTextContent("fmt.Println(8080)");
    expect(screen.getByText("Docker")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy code" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument());
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("fmt.Println(8080)");
  });

  it("renders a Bug Report and reports copy failure", async () => {
    useAiMemoTemplateMock.mockReturnValue({ data: bugTemplate } as ReturnType<typeof useAiMemoTemplate>);
    navigator.clipboard.writeText = vi.fn().mockRejectedValue(new Error("denied"));

    render(<AiMemoTemplate memoId="memo-bug" />);

    expect(screen.getByText("FastAPI startup failure")).toBeInTheDocument();
    expect(screen.getByText("Python 3.12 / Ubuntu 22")).toBeInTheDocument();
    expect(screen.getByText("ModuleNotFoundError")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy code" })).not.toBeInTheDocument();
  });

  it("stays hidden when the AI Service is not configured or no template exists", () => {
    vi.stubEnv("VITE_AI_SERVICE_URL", "");
    useAiMemoTemplateMock.mockReturnValue({ data: undefined } as ReturnType<typeof useAiMemoTemplate>);

    render(<AiMemoTemplate memoId="memo-plain" />);

    expect(screen.queryByTestId("ai-template-panel")).not.toBeInTheDocument();
  });
});
