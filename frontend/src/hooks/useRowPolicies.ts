import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../lib/apiClient";
import type { FilterCondition, RowLevelPolicy } from "../types";

export function useRowPolicies(tableId: string | undefined) {
  return useQuery({
    queryKey: ["row-policies", tableId],
    queryFn: async () => (await apiClient.get<RowLevelPolicy[]>(`/api/tables/${tableId}/row-level-policies`)).data,
    enabled: !!tableId,
    retry: false,
  });
}

export function useSetRowPolicy(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ targetUserId, filter }: { targetUserId: string; filter: FilterCondition }) =>
      (
        await apiClient.post<RowLevelPolicy>(`/api/tables/${tableId}/row-level-policies`, {
          target_user_id: targetUserId,
          filter,
        })
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["row-policies", tableId] }),
  });
}

export function useDeleteRowPolicy(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (policyId: string) => apiClient.delete(`/api/tables/${tableId}/row-level-policies/${policyId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["row-policies", tableId] }),
  });
}
