import { getAccessToken } from "@/auth-state";

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

export type AiInsightType = "fact" | "decision" | "action" | "bug";
export type AiInsightStatus = "pending" | "accepted" | "rejected";

export interface AiMemoInsight {
  insight_id: string;
  memo_id: string;
  insight_type: AiInsightType;
  title: string;
  summary: string;
  confidence: number;
  status: AiInsightStatus;
  source_refs: string[];
  version: number;
  created_at: string;
  updated_at: string;
}

export interface AiEvidenceCitation {
  memo_id: string;
  title: string;
  summary: string;
  source_refs: string[];
}

export interface AiEvidenceTraceStep {
  index: number;
  name: "search_memos" | "answer_from_evidence" | "refuse_unsafe_request";
  status: "completed";
  result_count?: number;
}

export interface AiEvidenceAnswer {
  answer: string;
  citations: AiEvidenceCitation[];
  trace: {
    terminal_state: "answered" | "no_context" | "refused";
    steps: AiEvidenceTraceStep[];
  };
}

export class AiEvidenceAnswerRequestError extends Error {
  constructor(public readonly status: number | null) {
    super("Evidence Answer request failed");
  }
}

export const getAiBffBasePath = (): string => {
  const configuredUrl = import.meta.env.VITE_AI_SERVICE_URL?.trim();
  return configuredUrl ? "/api/ai" : "";
};

export const isAiServiceConfigured = (): boolean => getAiBffBasePath().length > 0;

export const buildAiMemoNoteUrl = (memoId: string): string | null => {
  const baseUrl = getAiBffBasePath();
  if (!baseUrl || !memoId) return null;
  return baseUrl + "/notes/" + encodeURIComponent(memoId);
};

export const buildAiSummarizeUrl = (): string | null => {
  const baseUrl = getAiBffBasePath();
  return baseUrl ? baseUrl + "/summarize" : null;
};

export const buildAiMemoTemplateUrl = (memoId: string): string | null => {
  const baseUrl = getAiBffBasePath();
  if (!baseUrl || !memoId) return null;
  return `${baseUrl}/templates/${encodeURIComponent(memoId)}`;
};

export const buildAiMemoInsightsUrl = (memoId: string): string | null => {
  const baseUrl = getAiBffBasePath();
  if (!baseUrl || !memoId) return null;
  return `${baseUrl}/insights/${encodeURIComponent(memoId)}`;
};

export const buildAiMemoInsightStatusUrl = (insightId: string): string | null => {
  const baseUrl = getAiBffBasePath();
  if (!baseUrl || !insightId) return null;
  return `${baseUrl}/insights/${encodeURIComponent(insightId)}/status`;
};

const aiBffHeaders = (includeContentType = false): Record<string, string> => {
  const accessToken = getAccessToken();
  return {
    Accept: "application/json",
    ...(includeContentType ? { "Content-Type": "application/json" } : {}),
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };
};

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;

const readString = (value: unknown): string | null => (typeof value === "string" ? value : null);

const readTags = (value: unknown): string[] | null => {
  if (!Array.isArray(value) || !value.every((tag) => typeof tag === "string")) return null;
  return value;
};

const hasExactKeys = (value: Record<string, unknown>, keys: string[]): boolean => {
  const actualKeys = Object.keys(value);
  return actualKeys.length === keys.length && actualKeys.every((key) => keys.includes(key));
};

export const parseAiEvidenceAnswer = (value: unknown): AiEvidenceAnswer | null => {
  if (!isRecord(value) || !hasExactKeys(value, ["answer", "citations", "trace"])) return null;

  const answer = readString(value.answer);
  if (answer === null || !Array.isArray(value.citations)) {
    return null;
  }

  const citations = value.citations.map((citation): AiEvidenceCitation | null => {
    if (!isRecord(citation) || !hasExactKeys(citation, ["memo_id", "title", "summary", "source_refs"])) return null;
    const memoId = readString(citation.memo_id);
    const title = readString(citation.title);
    const summary = readString(citation.summary);
    const sourceRefs = readTags(citation.source_refs);
    if (memoId === null || title === null || summary === null || sourceRefs === null) {
      return null;
    }
    return { memo_id: memoId, title, summary, source_refs: sourceRefs };
  });
  if (citations.some((citation) => citation === null)) return null;

  if (!isRecord(value.trace) || !hasExactKeys(value.trace, ["terminal_state", "steps"]) || !Array.isArray(value.trace.steps)) return null;
  const terminalState = value.trace.terminal_state;
  if (terminalState !== "answered" && terminalState !== "no_context" && terminalState !== "refused") return null;
  const steps = value.trace.steps.map((step): AiEvidenceTraceStep | null => {
    if (!isRecord(step)) return null;
    const hasResultCount = Object.hasOwn(step, "result_count");
    if (!hasExactKeys(step, hasResultCount ? ["index", "name", "status", "result_count"] : ["index", "name", "status"])) return null;
    if (!Number.isInteger(step.index) || step.status !== "completed") return null;
    if (step.index === 1 && step.name === "refuse_unsafe_request" && !hasResultCount) {
      return { index: step.index, name: step.name, status: step.status };
    }
    if (step.index === 1 && step.name === "search_memos" && Number.isInteger(step.result_count) && step.result_count === citations.length) {
      return { index: step.index, name: step.name, status: step.status, result_count: step.result_count };
    }
    if (step.index === 2 && step.name === "answer_from_evidence" && !hasResultCount) {
      return { index: step.index, name: step.name, status: step.status };
    }
    return null;
  });
  if (
    steps.some((step) => step === null) ||
    (terminalState === "answered" &&
      (steps.length !== 2 || steps[0]?.name !== "search_memos" || steps[1]?.name !== "answer_from_evidence")) ||
    (terminalState === "no_context" && (steps.length !== 1 || steps[0]?.name !== "search_memos")) ||
    (terminalState === "refused" &&
      (steps.length !== 1 ||
        steps[0]?.name !== "refuse_unsafe_request" ||
        citations.length !== 0 ||
        answer !== "Request refused by the Agent safety policy."))
  ) {
    return null;
  }

  return {
    answer,
    citations: citations as AiEvidenceCitation[],
    trace: { terminal_state: terminalState, steps: steps as AiEvidenceTraceStep[] },
  };
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

export const parseAiMemoInsight = (value: unknown): AiMemoInsight | null => {
  if (!isRecord(value)) return null;
  const insightId = readString(value.insight_id);
  const memoId = readString(value.memo_id);
  const insightType = value.insight_type;
  const title = readString(value.title);
  const summary = readString(value.summary);
  const confidence = typeof value.confidence === "number" ? value.confidence : null;
  const status = value.status;
  const sourceRefs = readTags(value.source_refs);
  const version = typeof value.version === "number" ? value.version : null;
  const createdAt = readString(value.created_at);
  const updatedAt = readString(value.updated_at);
  if (
    insightId === null ||
    memoId === null ||
    !["fact", "decision", "action", "bug"].includes(String(insightType)) ||
    title === null ||
    summary === null ||
    confidence === null ||
    !["pending", "accepted", "rejected"].includes(String(status)) ||
    sourceRefs === null ||
    version === null ||
    createdAt === null ||
    updatedAt === null
  ) {
    return null;
  }
  return {
    insight_id: insightId,
    memo_id: memoId,
    insight_type: insightType as AiInsightType,
    title,
    summary,
    confidence,
    status: status as AiInsightStatus,
    source_refs: sourceRefs,
    version,
    created_at: createdAt,
    updated_at: updatedAt,
  };
};

export async function getAiMemoTemplate(memoId: string, signal?: AbortSignal): Promise<AiMemoTemplate | null> {
  const url = buildAiMemoTemplateUrl(memoId);
  if (!url) return null;

  const response = await fetch(url, {
    headers: aiBffHeaders(),
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
    headers: aiBffHeaders(),
    signal,
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("AI note request failed with status " + response.status);

  return parseAiMemoNote(await response.json());
}

export async function getAiMemoInsights(memoId: string, signal?: AbortSignal): Promise<AiMemoInsight[]> {
  const url = buildAiMemoInsightsUrl(memoId);
  if (!url) return [];

  const response = await fetch(url, { headers: aiBffHeaders(), signal });
  if (!response.ok) throw new Error(`AI insights request failed with status ${response.status}`);
  const payload: unknown = await response.json();
  if (!Array.isArray(payload)) throw new Error("AI insights response was invalid");
  return payload.map(parseAiMemoInsight).filter((item): item is AiMemoInsight => item !== null);
}

export async function updateAiMemoInsightStatus(
  memoId: string,
  insightId: string,
  status: Exclude<AiInsightStatus, "pending">,
  version: number,
): Promise<AiMemoInsight> {
  const url = buildAiMemoInsightStatusUrl(insightId);
  if (!url) throw new Error("AI Service is not configured");
  const response = await fetch(url, {
    method: "POST",
    headers: aiBffHeaders(true),
    body: JSON.stringify({ memo_id: memoId, status, version }),
  });
  if (response.status === 409) throw new Error("AI insight is stale; refresh and try again");
  if (!response.ok) throw new Error(`AI insight status update failed with status ${response.status}`);
  const insight = parseAiMemoInsight(await response.json());
  if (!insight) throw new Error("AI insight response was invalid");
  return insight;
}

export async function summarizeAiMemo(request: AiSummarizeRequest): Promise<AiMemoNote> {
  const url = buildAiSummarizeUrl();
  if (!url) throw new Error("AI Service is not configured");

  const response = await fetch(url, {
    method: "POST",
    headers: aiBffHeaders(true),
    body: JSON.stringify({ memo_id: request.memo_id }),
  });
  if (!response.ok) throw new Error("AI summary request failed with status " + response.status);

  const note = parseAiMemoNote(await response.json());
  if (!note) throw new Error("AI summary response was invalid");
  return note;
}

export async function requestAiEvidenceAnswer(question: string, limit: number, signal?: AbortSignal): Promise<AiEvidenceAnswer> {
  const accessToken = getAccessToken();
  const response = await fetch("/api/ai/agent/answer", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({ question, limit }),
    signal,
  });
  if (!response.ok) throw new AiEvidenceAnswerRequestError(response.status);

  const answer = parseAiEvidenceAnswer(await response.json());
  if (!answer) throw new AiEvidenceAnswerRequestError(null);
  return answer;
}
