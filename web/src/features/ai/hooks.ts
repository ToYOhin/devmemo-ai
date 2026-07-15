import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getAiMemoInsights,
  getAiMemoNote,
  getAiMemoTemplate,
  isAiServiceConfigured,
  summarizeAiMemo,
  updateAiMemoInsightStatus,
} from "./api";

export const aiTemplateKeys = {
  all: ["ai-templates"] as const,
  detail: (memoId: string) => [...aiTemplateKeys.all, memoId] as const,
};

export function useAiMemoTemplate(memoId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: aiTemplateKeys.detail(memoId),
    queryFn: ({ signal }) => getAiMemoTemplate(memoId, signal),
    enabled: (options?.enabled ?? true) && Boolean(memoId) && isAiServiceConfigured(),
    retry: false,
    staleTime: 1000 * 60,
  });
}

export const aiNoteKeys = {
  all: ["ai-notes"] as const,
  detail: (memoId: string) => [...aiNoteKeys.all, memoId] as const,
};

export const aiInsightKeys = {
  all: ["ai-insights"] as const,
  detail: (memoId: string) => [...aiInsightKeys.all, memoId] as const,
};

export function useAiMemoInsights(memoId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: aiInsightKeys.detail(memoId),
    queryFn: ({ signal }) => getAiMemoInsights(memoId, signal),
    enabled: (options?.enabled ?? true) && Boolean(memoId) && isAiServiceConfigured(),
    retry: false,
    staleTime: 1000 * 30,
  });
}

export function useAiMemoInsightsForMemos(memoIds: string[]) {
  return useQueries({
    queries: memoIds.map((memoId) => ({
      queryKey: aiInsightKeys.detail(memoId),
      queryFn: ({ signal }: { signal: AbortSignal }) => getAiMemoInsights(memoId, signal),
      enabled: Boolean(memoId) && isAiServiceConfigured(),
      retry: false,
      staleTime: 1000 * 30,
    })),
  });
}

export function useUpdateAiMemoInsightStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ insightId, status, version }: { insightId: string; status: "accepted" | "rejected"; version: number }) =>
      updateAiMemoInsightStatus(insightId, status, version),
    onSuccess: (insight) => {
      queryClient.invalidateQueries({ queryKey: aiInsightKeys.detail(insight.memo_id) });
    },
  });
}

export function useAiMemoNote(memoId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: aiNoteKeys.detail(memoId),
    queryFn: ({ signal }) => getAiMemoNote(memoId, signal),
    enabled: (options?.enabled ?? true) && Boolean(memoId) && isAiServiceConfigured(),
    retry: false,
    staleTime: 1000 * 60,
  });
}

export function useGenerateAiMemoSummary() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: summarizeAiMemo,
    onSuccess: (note, request) => {
      queryClient.setQueryData(aiNoteKeys.detail(request.memo_id), note);
      queryClient.invalidateQueries({ queryKey: aiInsightKeys.detail(request.memo_id) });
    },
  });
}
