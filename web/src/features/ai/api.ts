export type AiTemplateKind = "code" | "bug";

export interface AiCodeSnippet {
  title: string;
  language: string;
  code: string;
  description: string;
  tags: string[];
}

export interface AiBugReport {
  title: string;
  environment: string;
  error: string;
  reproduction_steps: string;
  root_cause: string;
  solution: string;
  tags: string[];
}

export interface AiMemoTemplate {
  memo_id: string | number;
  kind: AiTemplateKind;
  payload: AiCodeSnippet | AiBugReport;
  raw_content: string;
  created_at: string;
  updated_at: string;
}

export interface AiMemoNote {
  memo_id: string | number;
  summary: string;
  keywords: string[];
  category: string;
  suggested_tags: string[];
  provider: string;
  created_at: string;
}

export interface AiSummarizeRequest {
  memo_id: string;
  title: string;
  content: string;
  tags: string[];
}

export const getAiServiceUrl = (): string => {
  const configuredUrl = import.meta.env.VITE_AI_SERVICE_URL?.trim();
  return configuredUrl ? configuredUrl.replace(/\/+$/, "") : "";
};

export const isAiServiceConfigured = (): boolean => getAiServiceUrl().length > 0;

export const buildAiMemoNoteUrl = (memoId: string): string | null => {
  const baseUrl = getAiServiceUrl();
  if (!baseUrl || !memoId) return null;
  return baseUrl + "/api/ai/notes/" + encodeURIComponent(memoId);
};

export const buildAiSummarizeUrl = (): string | null => {
  const baseUrl = getAiServiceUrl();
  return baseUrl ? baseUrl + "/api/ai/summarize" : null;
};

export const buildAiMemoTemplateUrl = (memoId: string): string | null => {
  const baseUrl = getAiServiceUrl();
  if (!baseUrl || !memoId) return null;
  return `${baseUrl}/api/ai/templates/${encodeURIComponent(memoId)}`;
};

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;

const readString = (value: unknown): string | null => (typeof value === "string" ? value : null);

const readTags = (value: unknown): string[] | null => {
  if (!Array.isArray(value) || !value.every((tag) => typeof tag === "string")) return null;
  return value;
};

export const parseAiMemoNote = (value: unknown): AiMemoNote | null => {
  if (!isRecord(value)) return null;
  const memoId = typeof value.memo_id === "string" || typeof value.memo_id === "number" ? value.memo_id : null;
  const summary = readString(value.summary);
  const keywords = readTags(value.keywords);
  const category = readString(value.category);
  const suggestedTags = readTags(value.suggested_tags);
  const provider = readString(value.provider);
  const createdAt = readString(value.created_at);
  if (
    memoId === null ||
    summary === null ||
    keywords === null ||
    category === null ||
    suggestedTags === null ||
    provider === null ||
    createdAt === null
  ) {
    return null;
  }
  return { memo_id: memoId, summary, keywords, category, suggested_tags: suggestedTags, provider, created_at: createdAt };
};

export const parseAiMemoTemplate = (value: unknown): AiMemoTemplate | null => {
  if (!isRecord(value)) return null;

  const memoId = typeof value.memo_id === "string" || typeof value.memo_id === "number" ? value.memo_id : null;
  const rawContent = readString(value.raw_content);
  const createdAt = readString(value.created_at);
  const updatedAt = readString(value.updated_at);
  const payload = isRecord(value.payload) ? value.payload : null;
  if (memoId === null || rawContent === null || createdAt === null || updatedAt === null || payload === null) return null;

  const kind = value.kind;
  const title = readString(payload.title);
  const tags = readTags(payload.tags);
  if (title === null || tags === null) return null;

  if (kind === "code") {
    const language = readString(payload.language);
    const code = readString(payload.code);
    const description = readString(payload.description);
    if (language === null || code === null || description === null) return null;
    return {
      memo_id: memoId,
      kind,
      payload: { title, language, code, description, tags },
      raw_content: rawContent,
      created_at: createdAt,
      updated_at: updatedAt,
    };
  }

  if (kind === "bug") {
    const environment = readString(payload.environment);
    const error = readString(payload.error);
    const reproductionSteps = readString(payload.reproduction_steps);
    const rootCause = readString(payload.root_cause);
    const solution = readString(payload.solution);
    if (environment === null || error === null || reproductionSteps === null || rootCause === null || solution === null) return null;
    return {
      memo_id: memoId,
      kind,
      payload: {
        title,
        environment,
        error,
        reproduction_steps: reproductionSteps,
        root_cause: rootCause,
        solution,
        tags,
      },
      raw_content: rawContent,
      created_at: createdAt,
      updated_at: updatedAt,
    };
  }

  return null;
};

export async function getAiMemoTemplate(memoId: string, signal?: AbortSignal): Promise<AiMemoTemplate | null> {
  const url = buildAiMemoTemplateUrl(memoId);
  if (!url) return null;

  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`AI template request failed with status ${response.status}`);

  return parseAiMemoTemplate(await response.json());
}

export async function getAiMemoNote(memoId: string, signal?: AbortSignal): Promise<AiMemoNote | null> {
  const url = buildAiMemoNoteUrl(memoId);
  if (!url) return null;

  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("AI note request failed with status " + response.status);

  return parseAiMemoNote(await response.json());
}

export async function summarizeAiMemo(request: AiSummarizeRequest): Promise<AiMemoNote> {
  const url = buildAiSummarizeUrl();
  if (!url) throw new Error("AI Service is not configured");

  const response = await fetch(url, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error("AI summary request failed with status " + response.status);

  const note = parseAiMemoNote(await response.json());
  if (!note) throw new Error("AI summary response was invalid");
  return note;
}
