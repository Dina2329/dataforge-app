import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient, apiErrorMessage } from "../lib/apiClient";
import { toast } from "../stores/toastStore";

export interface GroupCleanupFields {
  group_field: string;
  value_field: string;
  score_field: string;
}

export interface GroupCleanupPreview extends GroupCleanupFields {
  qualifying_groups: number;
  rows_to_delete: number;
  sample_group_values: string[];
}

export interface GroupCleanupResult {
  groups_deleted: number;
  rows_deleted: number;
}

// Not a useQuery -- the three field names are picked fresh in the dialog
// each time (see GroupCleanupDialog's docstring), so this is fetched
// on-demand via mutate() rather than auto-refetched off a stable query key.
export function usePreviewGroupCleanup(tableId: string | undefined) {
  return useMutation({
    mutationFn: async (fields: GroupCleanupFields) =>
      (
        await apiClient.get<GroupCleanupPreview>(`/api/tables/${tableId}/group-cleanup-preview`, {
          params: fields,
        })
      ).data,
  });
}

export function useExecuteGroupCleanup(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (fields: GroupCleanupFields) =>
      (await apiClient.post<GroupCleanupResult>(`/api/tables/${tableId}/group-cleanup`, fields)).data,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["records", tableId] });
      queryClient.invalidateQueries({ queryKey: ["records-page", tableId] });
      toast.success(
        result.groups_deleted === 0
          ? "Nothing qualified -- no rows deleted"
          : `Moved ${result.groups_deleted} data point(s) (${result.rows_deleted} row(s)) to missing term`,
      );
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not run cleanup")),
  });
}
