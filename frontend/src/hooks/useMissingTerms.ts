import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, apiErrorMessage } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import type {
  IgnoredTermRow,
  ImportResultRow,
  ImportSelection,
  MissingTermsApiConfig,
  MissingTermsConfig,
  MissingTermsJob,
  MissingTermsListResponse,
  PrerequestUpload,
  RecordRow,
} from "../types";
import { invalidateRecordsQueries } from "./useRecords";

export function usePrerequestUpload(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["prerequest", workspaceId],
    queryFn: async () => (await apiClient.get<PrerequestUpload | null>(`/api/workspaces/${workspaceId}/prerequest`)).data,
    enabled: !!workspaceId,
    retry: false,
  });
}

export function useReplacePrerequest(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const { data } = await apiClient.put<PrerequestUpload>(`/api/workspaces/${workspaceId}/prerequest`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prerequest", workspaceId] });
      toast.success("Prerequest list saved");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not save the prerequest list")),
  });
}

export function useDeletePrerequest(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => apiClient.delete(`/api/workspaces/${workspaceId}/prerequest`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["prerequest", workspaceId] });
      toast.success("Prerequest list deleted");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not delete the prerequest list")),
  });
}

export function useMissingTermsApiConfig(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["missing-terms-api-config", workspaceId],
    queryFn: async () => (await apiClient.get<MissingTermsApiConfig | null>(`/api/workspaces/${workspaceId}/missing-terms-api-config`)).data,
    enabled: !!workspaceId,
    retry: false,
  });
}

export function useUpsertMissingTermsApiConfig(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { api_url: string; headers: Record<string, string> | null }) =>
      (await apiClient.put<MissingTermsApiConfig>(`/api/workspaces/${workspaceId}/missing-terms-api-config`, payload)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["missing-terms-api-config", workspaceId] });
      toast.success("External API settings saved");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not save the external API settings")),
  });
}

export function useMissingTermsConfig(tableId: string | undefined) {
  return useQuery({
    queryKey: ["missing-terms-config", tableId],
    queryFn: async () => (await apiClient.get<MissingTermsConfig | null>(`/api/tables/${tableId}/missing-terms-config`)).data,
    enabled: !!tableId,
    retry: false,
  });
}

export function useUpsertMissingTermsConfig(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { estate: string | null; building: string | null; unit: string | null; field_mapping: Record<string, string> }) =>
      (await apiClient.put<MissingTermsConfig>(`/api/tables/${tableId}/missing-terms-config`, payload)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["missing-terms-config", tableId] });
      queryClient.invalidateQueries({ queryKey: ["missing-terms", tableId] });
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not save Missing Terms config")),
  });
}

// No pagination UI anymore -- the panel picks a term via cascading
// Sub-Domain -> Term Name dropdowns rather than scrolling cards, so one
// fetch of up to the backend's max (200) covers the dropdown's options
// directly. If a table genuinely has more than 200 missing terms, narrowing
// its scope (Estate/Building/Unit) in Missing Terms config is the way to
// cut that down, same as it already narrows the shared prerequest list.
export function useMissingTerms(tableId: string | undefined) {
  return useQuery({
    queryKey: ["missing-terms", tableId],
    queryFn: async () => (await apiClient.get<MissingTermsListResponse>(`/api/tables/${tableId}/missing-terms`, { params: { limit: 200 } })).data,
    enabled: !!tableId,
  });
}

// Only fetched when the "Ignored" list is actually opened -- it's not
// needed just to show the count (that comes from useMissingTerms' summary).
export function useIgnoredMissingTerms(tableId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["missing-terms-ignored", tableId],
    queryFn: async () => (await apiClient.get<IgnoredTermRow[]>(`/api/tables/${tableId}/missing-terms/ignored`)).data,
    enabled: !!tableId && enabled,
  });
}

export function useIgnoreMissingTerm(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { sub_domain: string; term_name: string }) => apiClient.post(`/api/tables/${tableId}/missing-terms/ignore`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["missing-terms", tableId] });
      queryClient.invalidateQueries({ queryKey: ["missing-terms-ignored", tableId] });
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not ignore this term")),
  });
}

export function useUnignoreMissingTerm(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { sub_domain: string; term_name: string }) => apiClient.post(`/api/tables/${tableId}/missing-terms/unignore`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["missing-terms", tableId] });
      queryClient.invalidateQueries({ queryKey: ["missing-terms-ignored", tableId] });
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not revert this ignored term")),
  });
}

// No global error toast -- a 422 (unconfigured) or 409 (duplicate submission)
// must surface inline so the user's filled-in rows aren't lost behind a
// toast that's already gone by the time they look back.
export function useCreateMissingTermsJob(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (rows: Record<string, unknown>[]) =>
      (await apiClient.post<MissingTermsJob>(`/api/tables/${tableId}/missing-terms-jobs`, { rows })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["missing-terms", tableId] });
      queryClient.invalidateQueries({ queryKey: ["missing-terms-jobs", tableId] });
    },
  });
}

export function useMissingTermsJobs(tableId: string | undefined) {
  return useQuery({
    queryKey: ["missing-terms-jobs", tableId],
    queryFn: async () => (await apiClient.get<MissingTermsJob[]>(`/api/tables/${tableId}/missing-terms-jobs`)).data,
    enabled: !!tableId,
    refetchInterval: (query) => {
      const jobs = query.state.data ?? [];
      return jobs.some((j) => j.status === "queued" || j.status === "running") ? 3000 : false;
    },
  });
}

export function useMissingTermsJob(jobId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["missing-terms-job", jobId],
    queryFn: async () => (await apiClient.get<MissingTermsJob>(`/api/missing-terms-jobs/${jobId}`)).data,
    enabled: !!jobId && enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 3000 : false;
    },
  });
}

export function useRetryMissingTermsJob(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: string) => (await apiClient.post<MissingTermsJob>(`/api/missing-terms-jobs/${jobId}/retry`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["missing-terms-jobs", tableId] }),
    onError: (err) => toast.error(apiErrorMessage(err, "Could not retry this job")),
  });
}

export function useDismissMissingTermsJob(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: string) => apiClient.post(`/api/missing-terms-jobs/${jobId}/dismiss`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["missing-terms-jobs", tableId] }),
  });
}

export function useImportMissingTermsResults(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ jobId, selections }: { jobId: string; selections: ImportSelection[] }) =>
      (await apiClient.post<{ results: ImportResultRow[] }>(`/api/missing-terms-jobs/${jobId}/import`, { selections })).data.results,
    onSuccess: (_, { jobId }) => {
      invalidateRecordsQueries(queryClient, tableId);
      queryClient.invalidateQueries({ queryKey: ["missing-terms", tableId] });
      queryClient.invalidateQueries({ queryKey: ["missing-terms-job", jobId] });
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not import the selected rows")),
  });
}

export function useManualInsertMissingTerm(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { sub_domain: string; term_name: string; values: Record<string, unknown>; on_conflict?: "skip" | "overwrite" }) =>
      (await apiClient.post<RecordRow>(`/api/tables/${tableId}/missing-terms/manual-insert`, payload)).data,
    onSuccess: () => {
      invalidateRecordsQueries(queryClient, tableId);
      queryClient.invalidateQueries({ queryKey: ["missing-terms", tableId] });
    },
  });
}
