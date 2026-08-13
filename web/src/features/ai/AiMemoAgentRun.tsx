import { AlertCircleIcon, DownloadIcon, FileTextIcon, LoaderCircleIcon, WandSparklesIcon } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useTranslate } from "@/utils/i18n";
import {
  type AiAgentRunArtifact,
  AiAgentRunRequestError,
  type AiAgentRunTaskKind,
  requestAiAgentRun,
  requestAiAgentRunArtifact,
} from "./api";

interface Props {
  memoId: string;
}

const TASK_KIND: AiAgentRunTaskKind = "project_summary";

const AiMemoAgentRun = ({ memoId }: Props) => {
  const t = useTranslate();
  const [artifact, setArtifact] = useState<AiAgentRunArtifact | null>(null);
  const [phase, setPhase] = useState<"idle" | "running" | "succeeded">("idle");
  const [error, setError] = useState<"unavailable" | "auth" | "invalid" | "failed" | null>(null);

  const run = async () => {
    setArtifact(null);
    setError(null);
    setPhase("running");
    const requestKey = `memo-${memoId}-${TASK_KIND}-${Date.now()}`;
    try {
      const status = await requestAiAgentRun(TASK_KIND, requestKey, [memoId]);
      if (status.status !== "succeeded" || !status.artifact_id) {
        throw new AiAgentRunRequestError(null);
      }
      setArtifact(await requestAiAgentRunArtifact(status.run_id));
      setPhase("succeeded");
    } catch (requestError) {
      setPhase("idle");
      if (requestError instanceof AiAgentRunRequestError) {
        setError(
          requestError.status === 401
            ? "auth"
            : requestError.status === 400
              ? "invalid"
              : requestError.status === 404
                ? "unavailable"
                : "failed",
        );
      } else {
        setError("failed");
      }
    }
  };

  const download = () => {
    if (!artifact) return;
    const url = URL.createObjectURL(new Blob([artifact.markdown], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = artifact.file_name;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section data-testid="ai-agent-run-panel" className="mt-3 w-full overflow-hidden rounded-lg border border-primary/25 bg-card shadow-xs">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border/70 px-4 py-3">
        <div className="flex items-center gap-2">
          <WandSparklesIcon className="h-4 w-4 text-primary" />
          <div>
            <h2 className="text-sm font-semibold">{t("ai-agent-run.title")}</h2>
            <p className="text-xs text-muted-foreground">{t("ai-agent-run.description")}</p>
          </div>
        </div>
        <span className="rounded-full border border-primary/20 bg-primary/5 px-2 py-0.5 text-[11px] font-medium text-primary">
          {t("ai-agent-run.local-draft")}
        </span>
      </div>

      <div className="grid gap-4 p-4">
        <div className="rounded-md border border-primary/25 bg-primary/5 px-3 py-2">
          <span className="block text-sm font-medium">{t("ai-agent-run.task-project_summary")}</span>
          <span className="mt-0.5 block text-xs text-muted-foreground">{t("ai-agent-run.task-project_summary-description")}</span>
        </div>

        <ol
          aria-label={t("ai-agent-run.progress")}
          aria-live="polite"
          className="grid grid-cols-3 overflow-hidden rounded-md border border-border bg-muted/20"
        >
          {(["source", "runtime", "artifact"] as const).map((step, index) => {
            const complete = step === "source" || phase === "succeeded";
            const active = step === "runtime" && phase === "running";
            return (
              <li
                key={step}
                className={cn("min-w-0 border-r border-border px-2 py-2 last:border-r-0", (complete || active) && "bg-primary/5")}
              >
                <span className="block truncate text-[10px] uppercase tracking-wide text-muted-foreground">
                  {t(`ai-agent-run.step-${step}`)}
                </span>
                <span className="mt-1 flex items-center gap-1 truncate text-xs font-medium">
                  {active && <LoaderCircleIcon className="h-3 w-3 animate-spin motion-reduce:animate-none" />}
                  {t(complete ? "ai-agent-run.step-ready" : active ? "ai-agent-run.step-running" : "ai-agent-run.step-waiting")}
                </span>
                <span className="sr-only">{index + 1}</span>
              </li>
            );
          })}
        </ol>

        <Button className="w-fit" type="button" size="sm" disabled={phase === "running"} onClick={() => void run()}>
          {phase === "running" ? (
            <LoaderCircleIcon className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
          ) : (
            <FileTextIcon className="h-3.5 w-3.5" />
          )}
          {t(phase === "running" ? "ai-agent-run.running" : "ai-agent-run.run")}
        </Button>

        {error && (
          <p role="alert" data-testid="ai-agent-run-error" className="flex items-center gap-2 text-xs text-destructive">
            <AlertCircleIcon className="h-3.5 w-3.5" />
            {t(`ai-agent-run.error-${error}`)}
          </p>
        )}

        {artifact && (
          <div
            aria-live="polite"
            data-testid="ai-agent-run-artifact"
            className="grid gap-3 rounded-md border border-border bg-background p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-xs font-semibold">{t("ai-agent-run.artifact-ready")}</h3>
                <p className="text-xs text-muted-foreground">{artifact.file_name}</p>
              </div>
              <Button type="button" size="sm" variant="outline" onClick={download}>
                <DownloadIcon className="h-3.5 w-3.5" />
                {t("ai-agent-run.download")}
              </Button>
            </div>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded bg-muted/40 p-3 text-xs leading-relaxed">
              {artifact.markdown}
            </pre>
          </div>
        )}
      </div>
    </section>
  );
};

export default AiMemoAgentRun;
