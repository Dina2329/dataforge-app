import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, apiErrorMessage } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import type { RecordRow, RecordSubmitConfig } from "../types";
import { invalidateRecordsQueries } from "./useRecords";

export function useRecordSubmitConfig(tableId: string | undefined) {
  return useQuery({
    queryKey: ["record-submit-config", tableId],
    queryFn: async () => (await apiClient.get<RecordSubmitConfig | null>(`/api/tables/${tableId}/submit-config`)).data,
    enabled: !!tableId,
    retry: false,
  });
}

export function useUpsertRecordSubmitConfig(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { url: string; headers: Record<string, string> | null; status_field_id: string }) =>
      (await apiClient.put<RecordSubmitConfig>(`/api/tables/${tableId}/submit-config`, payload)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["record-submit-config", tableId] });
      toast.success("Submit settings saved");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not save submit settings")),
  });
}

export function useSubmitRow(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (rowId: number) => (await apiClient.post<RecordRow>(`/api/tables/${tableId}/rows/${rowId}/submit`)).data,
    onSuccess: () => {
      invalidateRecordsQueries(queryClient, tableId);
      toast.success("Row submitted");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not submit row")),
  });
}
