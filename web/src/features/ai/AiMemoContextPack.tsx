import { AlertCircleIcon, CheckIcon, ClipboardIcon, FileJsonIcon, PackageOpenIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { useInfiniteMemos } from "@/hooks/useMemoQueries";
import { cn } from "@/lib/utils";
import { useTranslate } from "@/utils/i18n";
import { type AiMemoInsight, isAiServiceConfigured } from "./api";
import { type AiContextPackResponse, buildContextPack } from "./contextPack";
import { useAiMemoInsightsForMemos } from "./hooks";

interface AiMemoContextPackProps {
  memoId: string;
  memoTitle: string;
}

interface AvailableMemo {
  memoId: string;
  title: string;
}

const normalizeMemoId = (name: string) => (name.startsWith("memos/") ? name.slice("memos/".length) : name);

const copyTextToClipboard = async (text: string) => {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // Fall through to the legacy DOM copy path for restricted browser contexts.
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand?.("copy") ?? false;
  textarea.remove();
  if (!copied) {
    throw new Error("clipboard unavailable");
  }
};

const AiMemoContextPack = ({ memoId, memoTitle }: AiMemoContextPackProps) => {
  const t = useTranslate();
  const aiConfigured = isAiServiceConfigured();
  const visibleMemosQuery = useInfiniteMemos({ pageSize: 50 }, { enabled: aiConfigured });
  const availableMemos = useMemo<AvailableMemo[]>(() => {
    const listedMemos = visibleMemosQuery.data?.pages.flatMap((page) => page.memos) ?? [];
    const listed = listedMemos
      .map((memo) => ({ memoId: normalizeMemoId(memo.name), title: memo.property?.title?.trim() || normalizeMemoId(memo.name) }))
      .filter((memo) => memo.memoId !== memoId);
    return [
      { memoId, title: memoTitle },
      ...listed.filter((memo, index) => listed.findIndex((item) => item.memoId === memo.memoId) === index),
    ];
  }, [memoId, memoTitle, visibleMemosQuery.data?.pages]);

  const [selectedMemoIds, setSelectedMemoIds] = useState<string[]>([memoId]);
  const [question, setQuestion] = useState("");
  const [maxChars, setMaxChars] = useState(2000);
  const [maxItems, setMaxItems] = useState(8);
  const [selectedInsightIds, setSelectedInsightIds] = useState<string[]>([]);
  const [copiedFormat, setCopiedFormat] = useState<"markdown" | "json" | null>(null);
  const [copyError, setCopyError] = useState(false);

  useEffect(() => {
    setSelectedMemoIds((current) => {
      const visibleIds = new Set(availableMemos.map((memo) => memo.memoId));
      const retained = current.filter((id) => visibleIds.has(id));
      return retained.includes(memoId) ? retained : [memoId, ...retained];
    });
  }, [availableMemos, memoId]);

  const insightQueries = useAiMemoInsightsForMemos(selectedMemoIds);
  const insightsByMemo = useMemo(() => {
    const result = new Map<string, AiMemoInsight[]>();
    selectedMemoIds.forEach((selectedId, index) => {
      result.set(selectedId, insightQueries[index]?.data ?? []);
    });
    return result;
  }, [insightQueries, selectedMemoIds]);
  const selectedInsights = useMemo(
    () => selectedMemoIds.flatMap((selectedId) => insightsByMemo.get(selectedId) ?? []),
    [insightsByMemo, selectedMemoIds],
  );
  const acceptedInsights = useMemo(() => selectedInsights.filter((insight) => insight.status === "accepted"), [selectedInsights]);
  const acceptedInsightIds = acceptedInsights.map((insight) => insight.insight_id);

  useEffect(() => {
    setSelectedInsightIds((current) => {
      const eligible = new Set(acceptedInsightIds);
      const retained = current.filter((id) => eligible.has(id));
      return [...retained, ...acceptedInsightIds.filter((id) => !retained.includes(id))];
    });
  }, [acceptedInsightIds.join(",")]);

  const usableSelectedMemoIds = selectedMemoIds.filter((selectedId, index) => selectedId === memoId || !insightQueries[index]?.isError);
  const usableSelectedMemos = availableMemos.filter((memo) => usableSelectedMemoIds.includes(memo.memoId));
  const packState = useMemo<{ response: AiContextPackResponse | null; error: boolean }>(() => {
    try {
      return {
        response: buildContextPack(
          {
            question: question || t("ai-context-pack.default-question"),
            memoIds: usableSelectedMemoIds,
            insightIds: selectedInsightIds,
            maxChars,
            maxItems,
          },
          Object.fromEntries(usableSelectedMemos.map((memo) => [memo.memoId, { memoId: memo.memoId, title: memo.title }])),
          Object.fromEntries(acceptedInsights.map((insight) => [insight.insight_id, insight])),
        ),
        error: false,
      };
    } catch {
      return { response: null, error: true };
    }
  }, [acceptedInsights, maxChars, maxItems, question, selectedInsightIds, t, usableSelectedMemoIds, usableSelectedMemos]);

  if (!aiConfigured) return null;

  const currentQuery = insightQueries[selectedMemoIds.indexOf(memoId)];
  const isLoading = insightQueries.some((query) => query.isLoading);
  const isError = currentQuery?.isError ?? false;
  const hasUnavailableAdditionalInsights = selectedMemoIds.some(
    (selectedId, index) => selectedId !== memoId && insightQueries[index]?.isError,
  );

  const toggleMemo = (selected: boolean, selectedId: string) => {
    if (selected) {
      setSelectedMemoIds((current) => (current.includes(selectedId) ? current : [...current, selectedId]));
      return;
    }
    setSelectedMemoIds((current) => current.filter((id) => id !== selectedId));
    const removedInsightIds = new Set((insightsByMemo.get(selectedId) ?? []).map((insight) => insight.insight_id));
    setSelectedInsightIds((current) => current.filter((id) => !removedInsightIds.has(id)));
  };

  const handleCopy = async (format: "markdown" | "json") => {
    if (!packState.response) {
      setCopyError(true);
      return;
    }
    try {
      await copyTextToClipboard(format === "markdown" ? packState.response.markdown : packState.response.toJson());
      setCopiedFormat(format);
      setCopyError(false);
    } catch {
      setCopyError(true);
    }
  };

  return (
    <section data-testid="ai-context-pack-panel" className="mt-3 w-full rounded-lg border border-primary/20 bg-card p-4 shadow-xs">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <PackageOpenIcon className="h-4 w-4 text-primary" />
          <div>
            <h2 className="text-sm font-semibold">{t("ai-context-pack.title")}</h2>
            <p className="text-xs text-muted-foreground">{t("ai-context-pack.description")}</p>
          </div>
        </div>
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">context-pack-v1</span>
      </div>

      {isLoading ? (
        <p className="mt-3 text-xs text-muted-foreground">{t("ai-context-pack.loading")}</p>
      ) : isError ? (
        <p data-testid="ai-context-pack-error" className="mt-3 flex items-center gap-2 text-xs text-destructive">
          <AlertCircleIcon className="h-3.5 w-3.5" />
          {t("ai-context-pack.load-failed")}
        </p>
      ) : (
        <div className="mt-4 grid gap-4">
          <label className="grid gap-1 text-xs font-medium">
            {t("ai-context-pack.question")}
            <textarea
              aria-label={t("ai-context-pack.question")}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={t("ai-context-pack.default-question")}
              rows={2}
              className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm font-normal outline-none focus:ring-2 focus:ring-ring"
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-xs font-medium">
              {t("ai-context-pack.max-chars")}
              <input
                aria-label={t("ai-context-pack.max-chars")}
                type="number"
                min={64}
                max={20000}
                value={maxChars}
                onChange={(event) => setMaxChars(Number(event.target.value))}
                className="rounded-md border border-border bg-background px-3 py-2 text-sm font-normal outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
            <label className="grid gap-1 text-xs font-medium">
              {t("ai-context-pack.max-items")}
              <input
                aria-label={t("ai-context-pack.max-items")}
                type="number"
                min={1}
                max={50}
                value={maxItems}
                onChange={(event) => setMaxItems(Number(event.target.value))}
                className="rounded-md border border-border bg-background px-3 py-2 text-sm font-normal outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
          </div>

          <div className="grid gap-2">
            <p className="text-xs font-medium">{t("ai-context-pack.sources")}</p>
            {availableMemos.map((memo) => (
              <div key={memo.memoId} className="grid gap-2 rounded-md border border-border p-2">
                <label className="flex min-w-0 items-start gap-2 text-xs">
                  <input
                    aria-label={`${t("ai-context-pack.memo-source")} ${memo.title}`}
                    type="checkbox"
                    checked={selectedMemoIds.includes(memo.memoId)}
                    onChange={(event) => toggleMemo(event.target.checked, memo.memoId)}
                    className="mt-0.5 shrink-0"
                  />
                  <span className="min-w-0 wrap-break-word">
                    {memo.title} <span className="text-muted-foreground">({memo.memoId})</span>
                  </span>
                </label>
                {selectedMemoIds.includes(memo.memoId) &&
                  (insightsByMemo.get(memo.memoId) ?? [])
                    .filter((insight) => insight.status === "accepted")
                    .map((insight) => (
                      <label key={insight.insight_id} className="ml-5 flex min-w-0 items-start gap-2 text-xs">
                        <input
                          aria-label={`${t("ai-context-pack.insight-source")} ${insight.title}`}
                          type="checkbox"
                          checked={selectedInsightIds.includes(insight.insight_id)}
                          onChange={(event) =>
                            setSelectedInsightIds((current) =>
                              event.target.checked
                                ? [...current, insight.insight_id]
                                : current.filter((insightId) => insightId !== insight.insight_id),
                            )
                          }
                          className="mt-0.5 shrink-0"
                        />
                        <span className="min-w-0 wrap-break-word">
                          {insight.title} <span className="text-muted-foreground">({insight.insight_id})</span>
                        </span>
                      </label>
                    ))}
              </div>
            ))}
            {hasUnavailableAdditionalInsights && (
              <p data-testid="ai-context-pack-unavailable" className="text-xs text-amber-600 dark:text-amber-400">
                {t("ai-context-pack.insights-unavailable")}
              </p>
            )}
            <p className="text-xs text-muted-foreground">{t("ai-context-pack.explicit-selection")}</p>
          </div>

          {acceptedInsights.length === 0 ? (
            <p data-testid="ai-context-pack-empty" className="flex items-center gap-2 text-xs text-muted-foreground">
              <PackageOpenIcon className="h-3.5 w-3.5" />
              {t("ai-context-pack.empty")}
            </p>
          ) : packState.error || !packState.response ? (
            <p data-testid="ai-context-pack-build-error" className="text-xs text-destructive">
              {t("ai-context-pack.build-failed")}
            </p>
          ) : (
            <>
              {packState.response.truncated && (
                <p data-testid="ai-context-pack-truncated" className="text-xs text-amber-600 dark:text-amber-400">
                  {t("ai-context-pack.truncated")} ({packState.response.truncationReason})
                </p>
              )}
              <pre
                data-testid="ai-context-pack-preview"
                className="max-h-72 overflow-auto whitespace-pre-wrap wrap-break-word rounded-md border border-border bg-muted/20 p-3 text-xs"
              >
                {packState.response.markdown}
              </pre>
              <div className="flex flex-wrap gap-2">
                <Button type="button" size="sm" variant="secondary" onClick={() => void handleCopy("markdown")}>
                  {copiedFormat === "markdown" ? <CheckIcon className="h-3.5 w-3.5" /> : <ClipboardIcon className="h-3.5 w-3.5" />}
                  {copiedFormat === "markdown" ? t("ai-context-pack.copied") : t("ai-context-pack.copy-markdown")}
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => void handleCopy("json")}>
                  <FileJsonIcon className="h-3.5 w-3.5" />
                  {t("ai-context-pack.copy-json")}
                </Button>
                {copyError && (
                  <span data-testid="ai-context-pack-copy-error" className="self-center text-xs text-destructive">
                    {t("ai-context-pack.copy-failed")}
                  </span>
                )}
              </div>
              <div className="grid gap-1 text-xs text-muted-foreground">
                <p>{t("ai-context-pack.source-trace")}</p>
                <ul className="grid gap-1 pl-4">
                  {packState.response.sources.map((source) => (
                    <li key={source.sourceId} className={cn("wrap-break-word", source.sourceType === "memo" && "text-foreground")}>
                      {source.title} · {source.sourceId}
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
};

export default AiMemoContextPack;
