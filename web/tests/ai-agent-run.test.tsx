import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AiMemoAgentRun from "@/features/ai/AiMemoAgentRun";
import * as api from "@/features/ai/api";

vi.mock("@/utils/i18n", () => ({
  useTranslate: () => (key: string) =>
    ({
      "ai-agent-run.title": "Build a project artifact",
      "ai-agent-run.description": "Turn this Memo into a local draft.",
      "ai-agent-run.local-draft": "Local draft",
      "ai-agent-run.task-project_summary": "Project summary",
      "ai-agent-run.task-project_summary-description": "Project overview",
      "ai-agent-run.progress": "AgentRun progress",
      "ai-agent-run.step-source": "Current Memo",
      "ai-agent-run.step-runtime": "Bounded run",
      "ai-agent-run.step-artifact": "Markdown",
      "ai-agent-run.step-ready": "Ready",
      "ai-agent-run.step-running": "Running",
      "ai-agent-run.step-waiting": "Waiting",
      "ai-agent-run.run": "Build draft",
      "ai-agent-run.running": "Building draft...",
      "ai-agent-run.artifact-ready": "Draft ready",
      "ai-agent-run.download": "Download Markdown",
      "ai-agent-run.error-unavailable": "AgentRun is not enabled.",
      "ai-agent-run.error-auth": "Sign in again.",
      "ai-agent-run.error-invalid": "Invalid Memo.",
      "ai-agent-run.error-failed": "The bounded run did not finish.",
    })[key] ?? key,
}));

const status: api.AiAgentRunStatus = {
  run_id: "run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  status: "succeeded",
  created_at: "2026-08-13T08:00:00Z",
  updated_at: "2026-08-13T08:00:01Z",
  last_event_seq: 6,
  source_count: 1,
  terminal_reason: null,
  artifact_id: "artifact-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AgentRun demo panel", () => {
  it("runs the fixed project summary for the current Memo and renders Markdown", async () => {
    const runSpy = vi.spyOn(api, "requestAiAgentRun").mockResolvedValue(status);
    vi.spyOn(api, "requestAiAgentRunArtifact").mockResolvedValue({
      artifact_id: status.artifact_id!,
      file_name: "project-summary.md",
      media_type: "text/markdown",
      markdown: "# Project summary\n\nBuilt an AgentRun BFF.\n",
      digest: "a".repeat(64),
    });

    render(<AiMemoAgentRun memoId="memo-42" />);
    expect(runSpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Build draft" }));

    await waitFor(() => expect(screen.getByTestId("ai-agent-run-artifact")).toBeInTheDocument());
    expect(runSpy).toHaveBeenCalledWith("project_summary", expect.any(String), ["memo-42"]);
    expect(screen.getByText("project-summary.md")).toBeInTheDocument();
    expect(screen.getByText(/Built an AgentRun BFF/)).toBeInTheDocument();
  });

  it("maps a disabled route to a directed unavailable state", async () => {
    vi.spyOn(api, "requestAiAgentRun").mockRejectedValue(new api.AiAgentRunRequestError(404));

    render(<AiMemoAgentRun memoId="memo-42" />);
    fireEvent.click(screen.getByRole("button", { name: "Build draft" }));

    await waitFor(() => expect(screen.getByTestId("ai-agent-run-error")).toHaveTextContent("AgentRun is not enabled."));
  });
});
