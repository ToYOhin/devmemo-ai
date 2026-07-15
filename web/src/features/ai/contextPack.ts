import type { AiMemoInsight } from "./api";

export interface AiContextPackRequest {
  question: string;
  memoIds: string[];
  insightIds: string[];
  maxChars: number;
  maxItems: number;
}

export interface AiContextPackMemo {
  memoId: string;
  title: string;
  summary?: string;
}

export interface AiContextPackItem {
  itemId: string;
  itemType: "memo" | "insight";
  memoId: string;
  insightId: string | null;
  title: string;
  summary: string;
  confidence: number | null;
  sourceIds: string[];
}

export interface AiContextPackSource {
  sourceId: string;
  sourceType: "memo" | "insight";
  memoId: string;
  insightId: string | null;
  title: string;
  sourceRefs: string[];
}

export interface AiContextPackResponse {
  packVersion: "context-pack-v1";
  question: string;
  markdown: string;
  items: AiContextPackItem[];
  sources: AiContextPackSource[];
  truncated: boolean;
  truncationReason: string | null;
  toJson: () => string;
}

export class AiContextPackValidationError extends Error {}

export function buildContextPack(
  request: AiContextPackRequest,
  memos: Record<string, AiContextPackMemo>,
  insights: Record<string, AiMemoInsight>,
): AiContextPackResponse {
  const memoIds = uniqueIds(request.memoIds, "memo");
  const insightIds = uniqueIds(request.insightIds, "insight");
  if (!request.question.trim()) throw new AiContextPackValidationError("question must not be empty");
  if (request.maxChars < 64 || request.maxChars > 20000) {
    throw new AiContextPackValidationError("maxChars must be between 64 and 20000");
  }
  if (request.maxItems < 1 || request.maxItems > 50) {
    throw new AiContextPackValidationError("maxItems must be between 1 and 50");
  }
  if (insightIds.length > 0 && memoIds.length === 0) {
    throw new AiContextPackValidationError("insight IDs must be explicitly selected with their memo IDs");
  }

  for (const memoId of memoIds) {
    if (!memos[memoId]) throw new AiContextPackValidationError(`unknown memo id: ${memoId}`);
  }
  for (const insightId of insightIds) {
    const insight = insights[insightId];
    if (!insight) throw new AiContextPackValidationError(`unknown insight id: ${insightId}`);
    if (insight.status !== "accepted") {
      throw new AiContextPackValidationError(`insight ${insightId} must be accepted before it enters a context pack`);
    }
    if (!memoIds.includes(insight.memo_id)) {
      throw new AiContextPackValidationError(`insight ${insightId} memo must be explicitly selected`);
    }
  }

  const selectedInsights = insightIds
    .map((insightId) => insights[insightId])
    .sort((left, right) => left.insight_id.localeCompare(right.insight_id))
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .sort((left, right) => right.confidence - left.confidence);
  const candidates = [
    ...memoIds.toSorted().map((memoId) => memoCandidate(memos[memoId])),
    ...selectedInsights.map((insight) => insightCandidate(insight, memos[insight.memo_id])),
  ];

  let markdown = packHeader(request.question, request.maxChars);
  const items: AiContextPackItem[] = [];
  const sources: AiContextPackSource[] = [];
  const sourceIds = new Set<string>();
  const truncationReasons = new Set<string>();

  for (const candidate of candidates) {
    if (items.length >= request.maxItems) {
      truncationReasons.add("max_items");
      break;
    }
    if (markdown.length + candidate.markdown.length > request.maxChars) {
      truncationReasons.add("max_chars");
      break;
    }
    markdown += candidate.markdown;
    items.push(candidate.item);
    for (const source of candidate.sources) {
      if (!sourceIds.has(source.sourceId)) {
        sourceIds.add(source.sourceId);
        sources.push(source);
      }
    }
  }

  const truncationReason = [...truncationReasons].sort().join(",") || null;
  const response = {
    packVersion: "context-pack-v1" as const,
    question: request.question.trim(),
    markdown,
    items,
    sources,
    truncated: truncationReason !== null,
    truncationReason,
  };

  return {
    ...response,
    toJson: () => JSON.stringify(response),
  };
}

interface Candidate {
  item: AiContextPackItem;
  sources: AiContextPackSource[];
  markdown: string;
}

function memoCandidate(memo: AiContextPackMemo): Candidate {
  const sourceId = `memo:${memo.memoId}`;
  const title = safeText(memo.title);
  const summary = safeText(memo.summary ?? "") || "No memo summary was provided.";
  const source: AiContextPackSource = {
    sourceId,
    sourceType: "memo",
    memoId: memo.memoId,
    insightId: null,
    title,
    sourceRefs: [],
  };
  return {
    item: {
      itemId: sourceId,
      itemType: "memo",
      memoId: memo.memoId,
      insightId: null,
      title,
      summary,
      confidence: null,
      sourceIds: [sourceId],
    },
    sources: [source],
    markdown: `## Memo \`${sourceId}\` — ${title}\nSummary: ${summary}\n\n`,
  };
}

function insightCandidate(insight: AiMemoInsight, memo: AiContextPackMemo): Candidate {
  const memoSourceId = `memo:${memo.memoId}`;
  const title = safeText(insight.title);
  const summary = safeText(insight.summary) || "No insight summary was provided.";
  const sourceRefs = [...new Set(insight.source_refs.map((ref) => safeText(ref, 160)).filter(Boolean))];
  const source: AiContextPackSource = {
    sourceId: insight.insight_id,
    sourceType: "insight",
    memoId: insight.memo_id,
    insightId: insight.insight_id,
    title,
    sourceRefs,
  };
  return {
    item: {
      itemId: insight.insight_id,
      itemType: "insight",
      memoId: insight.memo_id,
      insightId: insight.insight_id,
      title,
      summary,
      confidence: insight.confidence,
      sourceIds: [memoSourceId, insight.insight_id],
    },
    sources: [source],
    markdown: [
      `## Insight \`${insight.insight_id}\` — ${title}`,
      `- Memo: \`${insight.memo_id}\` — ${safeText(memo.title)}`,
      `- Type: ${insight.insight_type}`,
      `- Confidence: ${insight.confidence.toFixed(2)}`,
      `- Summary: ${summary}`,
      `- Source refs: ${sourceRefs.map((ref) => `\`${ref}\``).join(", ") || "none"}`,
      "",
    ].join("\n"),
  };
}

function uniqueIds(ids: string[], label: string): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (const rawId of ids) {
    const id = rawId.trim();
    if (!id) throw new AiContextPackValidationError(`${label} ID must not be empty`);
    if (!seen.has(id)) {
      seen.add(id);
      result.push(id);
    }
  }
  return result;
}

function packHeader(question: string, maxChars: number): string {
  const prefix = "# DevMemory Context Pack\n\nQuestion: ";
  const suffix = "\n\n";
  const available = maxChars - prefix.length - suffix.length;
  if (available <= 0) return `${prefix}${suffix}`.slice(0, maxChars);
  return `${prefix}${safeText(question, available)}${suffix}`;
}

function safeText(value: string, limit = 800): string {
  return value.replace(/`/g, "'").split(/\s+/).filter(Boolean).join(" ").slice(0, limit).trim();
}
