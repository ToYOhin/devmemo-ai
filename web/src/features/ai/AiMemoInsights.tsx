import { CheckIcon, CircleAlertIcon, LightbulbIcon, XIcon } from "lucide-react";
import { toast } from "react-hot-toast";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useTranslate } from "@/utils/i18n";
import { isAiServiceConfigured } from "./api";
import { useAiMemoInsights, useUpdateAiMemoInsightStatus } from "./hooks";

interface AiMemoInsightsProps {
  memoId: string;
}

const AiMemoInsights = ({ memoId }: AiMemoInsightsProps) => {
  const t = useTranslate();
  const { data: insights = [], isError } = useAiMemoInsights(memoId);
  const updateStatus = useUpdateAiMemoInsightStatus();

  if (!isAiServiceConfigured() || (!isError && insights.length === 0)) return null;

  const update = (insightId: string, status: "accepted" | "rejected", version: number) => {
    updateStatus.mutate(
      { insightId, status, version },
      {
        onError: (error) => toast.error(error instanceof Error ? error.message : t("ai-insights.update-failed")),
      },
    );
  };

  return (
    <section data-testid="ai-insights-panel" className="mt-3 w-full rounded-lg border border-primary/20 bg-card p-4 shadow-xs">
      <div className="flex items-center gap-2">
        <LightbulbIcon className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">{t("ai-insights.title")}</h2>
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{t("ai-insights.review")}</span>
      </div>
      {isError ? (
        <p className="mt-3 flex items-center gap-2 text-xs text-destructive">
          <CircleAlertIcon className="h-3.5 w-3.5" />
          {t("ai-insights.load-failed")}
        </p>
      ) : (
        <div className="mt-3 grid gap-2">
          {insights.map((insight) => (
            <article key={insight.insight_id} className="rounded-md border border-border bg-muted/10 p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium">{insight.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {t(`ai-insights.type-${insight.insight_type}`)} · {Math.round(insight.confidence * 100)}% ·{" "}
                    {t(`ai-insights.status-${insight.status}`)}
                  </p>
                </div>
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-xs",
                    insight.status === "accepted" && "bg-primary/10 text-primary",
                    insight.status === "rejected" && "bg-destructive/10 text-destructive",
                    insight.status === "pending" && "bg-muted text-muted-foreground",
                  )}
                >
                  {t(`ai-insights.status-${insight.status}`)}
                </span>
              </div>
              <p className="mt-2 text-sm whitespace-pre-wrap wrap-break-word">{insight.summary}</p>
              <p className="mt-2 text-xs text-muted-foreground">
                {t("ai-insights.sources")}: {insight.source_refs.join(", ")}
              </p>
              {insight.status === "pending" && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={updateStatus.isPending}
                    onClick={() => update(insight.insight_id, "accepted", insight.version)}
                  >
                    <CheckIcon className="h-3.5 w-3.5" />
                    {t("ai-insights.accept")}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={updateStatus.isPending}
                    onClick={() => update(insight.insight_id, "rejected", insight.version)}
                  >
                    <XIcon className="h-3.5 w-3.5" />
                    {t("ai-insights.reject")}
                  </Button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
};

export default AiMemoInsights;
