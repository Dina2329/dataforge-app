import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, apiErrorMessage } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import type { BatchSubmitConfig, BatchSubmitJob, BatchSubmitPreview, FilterExpr } from "../types";

export function useBatchSubmitConfig(tableId: string | undefined) {
  return useQuery({
    queryKey: ["batch-submit-config", tableId],
    queryFn: async () => (await apiClient.get<BatchSubmitConfig | null>(`/api/tables/${tableId}/batch-submit-config`)).data,
    enabled: !!tableId,
    retry: false,
  });
}

export function useUpsertBatchSubmitConfig(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { url: string; headers: Record<string, string> | null; filter: FilterExpr; batch_size: number }) =>
      (await apiClient.put<BatchSubmitConfig>(`/api/tables/${tableId}/batch-submit-config`, payload)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["batch-submit-config", tableId] });
      toast.success("Batch Submit settings saved");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not save Batch Submit settings")),
  });
}

// Fetched only while the Send dialog is actually open -- a read-only count
// of how many rows are currently marked, so the user sees what they're
// about to send before committing (enabled gates this, same reasoning as
// every other "only while this dialog is open" query in the app).
export function useBatchSubmitPreview(tableId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["batch-submit-preview", tableId],
    queryFn: async () => (await apiClient.get<BatchSubmitPreview>(`/api/tables/${tableId}/batch-submit-preview`)).data,
    enabled: !!tableId && enabled,
    retry: false,
  });
}

// No global error toast -- a 422 ("nothing marked" / "not configured yet")
// must surface inline in the Send dialog, not vanish behind a toast.
export function useCreateBatchSubmitJob(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await apiClient.post<BatchSubmitJob>(`/api/tables/${tableId}/batch-submit-jobs`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["batch-submit-jobs", tableId] }),
  });
}

export function useBatchSubmitJobs(tableId: string | undefined) {
  return useQuery({
    queryKey: ["batch-submit-jobs", tableId],
    queryFn: async () => (await apiClient.get<BatchSubmitJob[]>(`/api/tables/${tableId}/batch-submit-jobs`)).data,
    enabled: !!tableId,
    refetchInterval: (query) => {
      const jobs = query.state.data ?? [];
      return jobs.some((j) => j.status === "queued" || j.status === "running") ? 2000 : false;
    },
  });
}

export function useDismissBatchSubmitJob(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: string) => apiClient.post(`/api/batch-submit-jobs/${jobId}/dismiss`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["batch-submit-jobs", tableId] }),
  });
}
