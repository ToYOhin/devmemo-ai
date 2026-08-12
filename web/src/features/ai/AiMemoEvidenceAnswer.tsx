import { AlertCircleIcon, BotIcon, SearchIcon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { useTranslate } from "@/utils/i18n";
import { type AiEvidenceAnswer, AiEvidenceAnswerRequestError, requestAiEvidenceAnswer } from "./api";

const MAX_LIMIT = 10;
const DEMO_PROMPTS = ["project-overview", "recent-decisions", "open-actions"] as const;

const AiMemoEvidenceAnswer = () => {
  const t = useTranslate();
  const [opened, setOpened] = useState(false);
  const [question, setQuestion] = useState("");
  const [limit, setLimit] = useState(5);
  const [answer, setAnswer] = useState<AiEvidenceAnswer | null>(null);
  const [error, setError] = useState<"invalid" | "unavailable" | "auth" | "failed" | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || !Number.isInteger(limit) || limit < 1 || limit > MAX_LIMIT) {
      setAnswer(null);
      setError("invalid");
      return;
    }

    setIsSubmitting(true);
    setAnswer(null);
    setError(null);
    try {
      setAnswer(await requestAiEvidenceAnswer(trimmedQuestion, limit));
    } catch (requestError) {
      if (requestError instanceof AiEvidenceAnswerRequestError) {
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
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section data-testid="ai-evidence-answer-panel" className="mt-3 w-full rounded-lg border border-primary/20 bg-card p-4 shadow-xs">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <BotIcon className="h-4 w-4 text-primary" />
          <div>
            <h2 className="text-sm font-semibold">{t("ai-evidence-answer.title")}</h2>
            <p className="text-xs text-muted-foreground">{t("ai-evidence-answer.description")}</p>
          </div>
        </div>
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{t("ai-evidence-answer.experimental")}</span>
      </div>

      {!opened ? (
        <Button className="mt-4" type="button" size="sm" variant="outline" aria-expanded={false} onClick={() => setOpened(true)}>
          <SearchIcon className="h-3.5 w-3.5" />
          {t("ai-evidence-answer.start")}
        </Button>
      ) : (
        <form className="mt-4 grid gap-3" onSubmit={(event) => void submit(event)}>
          <label className="grid gap-1 text-xs font-medium">
            {t("ai-evidence-answer.question")}
            <textarea
              aria-label={t("ai-evidence-answer.question")}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={t("ai-evidence-answer.question-placeholder")}
              rows={2}
              className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm font-normal outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <fieldset className="grid gap-2">
            <legend className="text-xs font-medium text-muted-foreground">{t("ai-evidence-answer.try-example")}</legend>
            <div className="flex flex-wrap gap-2">
              {DEMO_PROMPTS.map((prompt) => {
                const value = t(`ai-evidence-answer.example-${prompt}`);
                return (
                  <Button key={prompt} type="button" size="sm" variant="outline" onClick={() => setQuestion(value)}>
                    {value}
                  </Button>
                );
              })}
            </div>
          </fieldset>
          <label className="grid max-w-48 gap-1 text-xs font-medium">
            {t("ai-evidence-answer.limit")}
            <input
              aria-label={t("ai-evidence-answer.limit")}
              type="number"
              min={1}
              max={MAX_LIMIT}
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm font-normal outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <Button className="w-fit" type="submit" size="sm" disabled={isSubmitting}>
            <SearchIcon className="h-3.5 w-3.5" />
            {isSubmitting ? t("ai-evidence-answer.submitting") : t("ai-evidence-answer.submit")}
          </Button>
        </form>
      )}

      {error && (
        <p data-testid="ai-evidence-answer-error" className="mt-3 flex items-center gap-2 text-xs text-destructive">
          <AlertCircleIcon className="h-3.5 w-3.5" />
          {t(`ai-evidence-answer.error-${error}`)}
        </p>
      )}

      {answer && (
        <div data-testid="ai-evidence-answer-result" className="mt-4 grid gap-3">
          <div>
            <h3 className="text-xs font-semibold">{t("ai-evidence-answer.answer")}</h3>
            <p className="mt-1 text-sm whitespace-pre-wrap wrap-break-word">{answer.answer}</p>
          </div>
          <div>
            <h3 className="text-xs font-semibold">{t("ai-evidence-answer.citations")}</h3>
            {answer.citations.length === 0 ? (
              <p className="mt-1 text-xs text-muted-foreground">{t("ai-evidence-answer.no-citations")}</p>
            ) : (
              <ol className="mt-2 grid gap-2">
                {answer.citations.map((citation, index) => (
                  <li key={`${citation.memo_id}-${index}`} className="rounded-md border border-border bg-muted/10 p-3 text-xs">
                    <p className="font-medium">{citation.title}</p>
                    <p className="mt-1 whitespace-pre-wrap wrap-break-word text-muted-foreground">{citation.summary}</p>
                    <p className="mt-2 text-muted-foreground">
                      {t("ai-evidence-answer.citation-source-refs")}: {citation.source_refs.join(", ")}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </div>
          <div>
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold">{t("ai-evidence-answer.trace")}</h3>
              <span
                data-testid="ai-evidence-answer-terminal-state"
                className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
              >
                {t(`ai-evidence-answer.trace-terminal-${answer.trace.terminal_state}`)}
              </span>
            </div>
            <ol className="mt-2 grid gap-1 text-xs text-muted-foreground">
              {answer.trace.steps.map((step) => (
                <li key={step.index} className="flex items-center justify-between gap-3 rounded-md bg-muted/30 px-2 py-1.5">
                  <span>
                    {step.index}. {t(`ai-evidence-answer.trace-${step.name}`)}
                    {step.result_count !== undefined &&
                      ` · ${t(step.result_count === 1 ? "ai-evidence-answer.trace-results_one" : "ai-evidence-answer.trace-results_other", { count: step.result_count })}`}
                  </span>
                  <span className="font-medium text-foreground">{t(`ai-evidence-answer.trace-status-${step.status}`)}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </section>
  );
};

export default AiMemoEvidenceAnswer;
