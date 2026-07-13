import { SparklesIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "react-hot-toast";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useTranslate } from "@/utils/i18n";
import { isAiServiceConfigured } from "./api";
import { useAiMemoNote, useGenerateAiMemoSummary } from "./hooks";

interface AiMemoSummaryProps {
  memoId: string;
  title: string;
  content: string;
  tags: string[];
}

const AiMemoSummary = ({ memoId, title, content, tags }: AiMemoSummaryProps) => {
  const t = useTranslate();
  const { data: note } = useAiMemoNote(memoId);
  const generateSummary = useGenerateAiMemoSummary();
  const [feedback, setFeedback] = useState<"success" | "error" | null>(null);

  if (!isAiServiceConfigured()) return null;

  const handleGenerate = () => {
    setFeedback(null);
    generateSummary.mutate(
      { memo_id: memoId, title, content, tags },
      {
        onSuccess: () => {
          setFeedback("success");
          toast.success(t("ai-summary.generated"));
        },
        onError: () => {
          setFeedback("error");
          toast.error(t("ai-summary.generate-failed"));
        },
      },
    );
  };

  const action = (
    <Button type="button" size="sm" variant={note ? "outline" : "secondary"} onClick={handleGenerate} disabled={generateSummary.isPending}>
      <SparklesIcon className="h-4 w-4" />
      {generateSummary.isPending ? t("ai-summary.generating") : note ? t("ai-summary.regenerate") : t("ai-summary.generate")}
    </Button>
  );

  if (!note) {
    return (
      <div data-testid="ai-summary-action" className="mt-3 flex flex-wrap items-center gap-2">
        {action}
        {feedback === "error" && (
          <span data-testid="ai-summary-feedback" className="text-xs text-destructive">
            {t("ai-summary.generate-failed")}
          </span>
        )}
      </div>
    );
  }

  return (
    <section data-testid="ai-summary-panel" className="mt-3 w-full rounded-lg border border-primary/20 bg-card p-4 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <SparklesIcon className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">{t("ai-summary.title")}</h2>
        </div>
        {action}
      </div>
      <dl className="mt-3 grid gap-3">
        <div className="flex flex-col gap-1">
          <dt className="text-xs font-medium text-muted-foreground">{t("ai-summary.summary")}</dt>
          <dd className="text-sm whitespace-pre-wrap wrap-break-word">{note.summary}</dd>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <dt className="text-xs font-medium text-muted-foreground">{t("ai-summary.keywords")}</dt>
            <dd className="flex flex-wrap gap-1">
              {note.keywords.map((keyword) => (
                <span key={keyword} className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                  {keyword}
                </span>
              ))}
            </dd>
          </div>
          <div className="flex flex-col gap-1">
            <dt className="text-xs font-medium text-muted-foreground">{t("ai-summary.category")}</dt>
            <dd className={cn("text-sm", !note.category && "text-muted-foreground")}>{note.category || "—"}</dd>
          </div>
        </div>
      </dl>
      {feedback && (
        <p data-testid="ai-summary-feedback" className={cn("mt-3 text-xs", feedback === "error" ? "text-destructive" : "text-primary")}>
          {feedback === "error" ? t("ai-summary.generate-failed") : t("ai-summary.generated")}
        </p>
      )}
    </section>
  );
};

export default AiMemoSummary;
