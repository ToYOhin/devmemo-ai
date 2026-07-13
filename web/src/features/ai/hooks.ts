import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAiMemoNote, getAiMemoTemplate, isAiServiceConfigured, summarizeAiMemo } from "./api";

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
    },
  });
}
