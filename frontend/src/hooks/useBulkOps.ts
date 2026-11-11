import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../lib/apiClient";
import type { BulkOperation, BulkUpdatePreview, FilterCondition } from "../types";
import { invalidateRecordsQueries } from "./useRecords";

export function usePreviewBulkUpdate(tableId: string | undefined) {
  return useMutation({
    mutationFn: async ({ filter, values }: { filter: FilterCondition; values: Record<string, unknown> }) =>
      (await apiClient.post<BulkUpdatePreview>(`/api/tables/${tableId}/bulk-update/preview`, { filter, values })).data,
  });
}

export function useExecuteBulkUpdate(tableId: string | undefined) {
  return useMutation({
    mutationFn: async ({ filter, values }: { filter: FilterCondition; values: Record<string, unknown> }) =>
      (
        await apiClient.post<BulkOperation>(`/api/tables/${tableId}/bulk-update/execute`, {
          filter,
          values,
          confirm: true,
        })
      ).data,
  });
}

export function useBulkOperationStatus(operationId: string | undefined, enabled: boolean, awaitingUndo = false) {
  return useQuery({
    queryKey: ["bulk-operation", operationId],
    queryFn: async () => (await apiClient.get<BulkOperation>(`/api/bulk-operations/${operationId}`)).data,
    enabled: !!operationId && enabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      const stillRunning = data?.status === "pending" || data?.status === "running";
      const stillUndoing = awaitingUndo && !data?.undone_at;
      return stillRunning || stillUndoing ? 800 : false;
    },
  });
}

export function useUndoBulkOperation(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (operationId: string) => (await apiClient.post<BulkOperation>(`/api/bulk-operations/${operationId}/undo`)).data,
    onSuccess: () => invalidateRecordsQueries(queryClient, tableId),
  });
}
