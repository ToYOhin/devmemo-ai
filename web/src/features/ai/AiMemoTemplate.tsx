import hljs from "highlight.js";
import { BugIcon, CheckIcon, Code2Icon, CopyIcon } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useTranslate } from "@/utils/i18n";
import type { AiBugReport, AiCodeSnippet, AiMemoTemplate } from "./api";
import { isAiServiceConfigured } from "./api";
import { useAiMemoTemplate } from "./hooks";

const languageAliases: Record<string, string> = {
  Python: "python",
  Go: "go",
  JavaScript: "javascript",
  TypeScript: "typescript",
  "C++": "cpp",
  SQL: "sql",
};

const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>"']/g,
    (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[character] ?? character,
  );

const highlightCode = (code: string, language: string): string => {
  const languageId = languageAliases[language] ?? language.toLowerCase();
  try {
    if (hljs.getLanguage(languageId)) {
      return hljs.highlight(code, { language: languageId }).value;
    }
  } catch {
    // Keep the code readable if a language definition is unavailable.
  }
  return escapeHtml(code);
};

const Field = ({ label, value, multiline = false }: { label: string; value: string; multiline?: boolean }) => (
  <div className="flex flex-col gap-1">
    <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
    <dd className={cn("text-sm whitespace-pre-wrap wrap-break-word", multiline && "font-mono text-xs", !value && "text-muted-foreground")}>
      {value || "—"}
    </dd>
  </div>
);

const CopyCodeButton = ({ code }: { code: string }) => {
  const t = useTranslate();
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");

  const handleCopy = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(code);
      setStatus("success");
    } catch {
      setStatus("error");
    }
  };

  return (
    <div className="flex items-center gap-2">
      {status === "error" && <span className="text-xs text-destructive">{t("ai-template.copy-failed")}</span>}
      <button
        type="button"
        onClick={handleCopy}
        className={cn(
          "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs transition-colors hover:bg-accent",
          status === "success" ? "text-primary" : "text-muted-foreground hover:text-foreground",
        )}
        aria-label={status === "success" ? t("ai-template.copied") : t("ai-template.copy")}
      >
        {status === "success" ? <CheckIcon className="h-3.5 w-3.5" /> : <CopyIcon className="h-3.5 w-3.5" />}
        <span>{status === "success" ? t("ai-template.copied") : t("ai-template.copy")}</span>
      </button>
    </div>
  );
};

const TemplateHeader = ({ template }: { template: AiMemoTemplate }) => {
  const t = useTranslate();
  const isCode = template.kind === "code";
  return (
    <div className="flex items-center gap-2">
      {isCode ? <Code2Icon className="h-4 w-4 text-primary" /> : <BugIcon className="h-4 w-4 text-primary" />}
      <h2 className="text-sm font-semibold">{t("ai-template.title")}</h2>
      <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
        {isCode ? t("ai-template.code-snippet") : t("ai-template.bug-report")}
      </span>
    </div>
  );
};

const CodeSnippetView = ({ payload }: { payload: AiCodeSnippet }) => {
  const t = useTranslate();
  return (
    <>
      <dl className="grid gap-3 sm:grid-cols-2">
        <Field label={t("common.title")} value={payload.title} />
        <Field label={t("common.language")} value={payload.language} />
        <div className="sm:col-span-2">
          <Field label={t("common.description")} value={payload.description} />
        </div>
      </dl>
      {payload.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {payload.tags.map((tag) => (
            <span key={tag} className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
              {tag}
            </span>
          ))}
        </div>
      )}
      <div className="overflow-hidden rounded-lg border border-border bg-muted/20">
        <div className="flex items-center justify-between border-b border-border bg-muted/30 px-2 py-1">
          <span className="text-xs text-muted-foreground">{payload.language}</span>
          <CopyCodeButton code={payload.code} />
        </div>
        <pre className="max-h-96 overflow-x-auto p-3 text-sm leading-relaxed">
          <code
            className={`language-${languageAliases[payload.language] ?? payload.language.toLowerCase()}`}
            dangerouslySetInnerHTML={{ __html: highlightCode(payload.code, payload.language) }}
          />
        </pre>
      </div>
    </>
  );
};

const BugReportView = ({ payload }: { payload: AiBugReport }) => {
  const t = useTranslate();
  return (
    <dl className="grid gap-3 sm:grid-cols-2">
      <Field label={t("common.title")} value={payload.title} />
      <Field label={t("ai-template.environment")} value={payload.environment} />
      <div className="sm:col-span-2">
        <Field label={t("ai-template.error")} value={payload.error} multiline />
      </div>
      <div className="sm:col-span-2">
        <Field label={t("ai-template.reproduction-steps")} value={payload.reproduction_steps} multiline />
      </div>
      <div className="sm:col-span-2">
        <Field label={t("ai-template.root-cause")} value={payload.root_cause} multiline />
      </div>
      <div className="sm:col-span-2">
        <Field label={t("ai-template.solution")} value={payload.solution} multiline />
      </div>
    </dl>
  );
};

interface AiMemoTemplateProps {
  memoId: string;
}

const AiMemoTemplate = ({ memoId }: AiMemoTemplateProps) => {
  const { data: template } = useAiMemoTemplate(memoId);

  if (!isAiServiceConfigured() || !template) return null;

  return (
    <section data-testid="ai-template-panel" className="mt-3 w-full rounded-lg border border-primary/20 bg-card p-4 shadow-xs">
      <TemplateHeader template={template} />
      <div className="mt-3 flex flex-col gap-3">
        {template.kind === "code" ? (
          <CodeSnippetView payload={template.payload as AiCodeSnippet} />
        ) : (
          <BugReportView payload={template.payload as AiBugReport} />
        )}
      </div>
    </section>
  );
};

export default AiMemoTemplate;
