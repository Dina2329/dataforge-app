import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, apiErrorMessage } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import type { Base, ColumnDef, DataSource, PendingSyncChange, SyncChangeBatch, TableRef, TableSyncConfig } from "../types";

export function useDataSources(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["data-sources", workspaceId],
    queryFn: async () => (await apiClient.get<DataSource[]>(`/api/workspaces/${workspaceId}/data-sources`)).data,
    enabled: !!workspaceId,
  });
}

export function useBase(baseId: string | undefined) {
  return useQuery({
    queryKey: ["base", baseId],
    queryFn: async () => (await apiClient.get<Base>(`/api/bases/${baseId}`)).data,
    enabled: !!baseId,
  });
}

export function useCreateDataSource(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      name,
      sourceType,
      config,
      file,
    }: {
      name: string;
      sourceType: string;
      config: Record<string, unknown>;
      file?: File;
    }) => {
      const form = new FormData();
      form.append("name", name);
      form.append("source_type", sourceType);
      form.append("config", JSON.stringify(config));
      if (file) form.append("file", file);
      const { data } = await apiClient.post<DataSource>(`/api/workspaces/${workspaceId}/data-sources`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
    onSuccess: (dataSource) => {
      queryClient.invalidateQueries({ queryKey: ["data-sources", workspaceId] });
      toast.success(`Connected "${dataSource.name}"`);
    },
  });
}

export function useDeleteDataSource(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (dataSourceId: string) => apiClient.delete(`/api/data-sources/${dataSourceId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["data-sources", workspaceId] });
      toast.success("Connection removed");
    },
  });
}

export function useTestDataSource() {
  return useMutation({
    mutationFn: async (dataSourceId: string) => apiClient.post(`/api/data-sources/${dataSourceId}/test`),
  });
}

export function useDataSourceTables(dataSourceId: string | undefined) {
  return useQuery({
    queryKey: ["data-source-tables", dataSourceId],
    queryFn: async () => (await apiClient.get<TableRef[]>(`/api/data-sources/${dataSourceId}/tables`)).data,
    enabled: !!dataSourceId,
  });
}

export function useDataSourceColumns(dataSourceId: string | undefined, table: TableRef | null) {
  return useQuery({
    queryKey: ["data-source-columns", dataSourceId, table?.name, table?.schema_name],
    queryFn: async () =>
      (
        await apiClient.get<ColumnDef[]>(`/api/data-sources/${dataSourceId}/tables/${table!.name}/columns`, {
          params: table!.schema_name ? { table_schema: table!.schema_name } : undefined,
        })
      ).data,
    enabled: !!dataSourceId && !!table,
  });
}

export function useImportFromSource(baseId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      dataSourceId,
      table,
      newTableName,
      syncEnabled,
    }: {
      dataSourceId: string;
      table: TableRef;
      newTableName: string;
      syncEnabled?: boolean;
    }) =>
      (
        await apiClient.post(`/api/bases/${baseId}/import-from-source/${dataSourceId}`, {
          table_name: table.name,
          table_schema: table.schema_name,
          new_table_name: newTableName,
          sync_enabled: syncEnabled ?? false,
        })
      ).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tables", baseId] });
      toast.success("Import complete");
    },
  });
}

export function useTableSync(tableId: string | undefined) {
  return useQuery({
    queryKey: ["table-sync", tableId],
    queryFn: async () => (await apiClient.get<TableSyncConfig | null>(`/api/tables/${tableId}/sync`)).data,
    enabled: !!tableId,
  });
}

export function useSetTableSyncEnabled(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (enabled: boolean) =>
      (await apiClient.patch<TableSyncConfig>(`/api/tables/${tableId}/sync`, { sync_enabled: enabled })).data,
    onSuccess: (config) => {
      queryClient.setQueryData(["table-sync", tableId], config);
      toast.success(config.sync_enabled ? "Sync resumed" : "Sync paused");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not update sync")),
  });
}

export function useSetPushRequiresApproval(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ syncEnabled, requiresApproval }: { syncEnabled: boolean; requiresApproval: boolean }) =>
      (
        await apiClient.patch<TableSyncConfig>(`/api/tables/${tableId}/sync`, {
          sync_enabled: syncEnabled,
          push_requires_approval: requiresApproval,
        })
      ).data,
    onSuccess: (config) => {
      queryClient.setQueryData(["table-sync", tableId], config);
      toast.success(config.push_requires_approval ? "Changes now require approval before pushing" : "Approval requirement removed");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not update approval setting")),
  });
}

// The caller's own not-yet-submitted edits on gated tables in this
// workspace -- what submitting would bundle up, before it's bundled.
export function useDraftSyncChanges(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["pending-sync-change-drafts", workspaceId],
    queryFn: async () => (await apiClient.get<PendingSyncChange[]>(`/api/workspaces/${workspaceId}/pending-sync-change-drafts`)).data,
    enabled: !!workspaceId,
  });
}

export function useSubmitSyncChangeDrafts(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      (await apiClient.post<{ batch_id: string; change_count: number }>(`/api/workspaces/${workspaceId}/pending-sync-changes/submit`)).data,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["pending-sync-change-drafts", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["sync-change-batches", workspaceId] });
      const word = data.change_count === 1 ? "change" : "changes";
      toast.success(`Submitted ${data.change_count} ${word} for approval`);
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not submit your changes")),
  });
}

// Open batches an owner/admin still needs to act on -- 403s for anyone else,
// which the page below treats as "nothing to review", not an error.
export function useSyncChangeBatches(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["sync-change-batches", workspaceId],
    queryFn: async () => (await apiClient.get<SyncChangeBatch[]>(`/api/workspaces/${workspaceId}/sync-change-batches`)).data,
    enabled: !!workspaceId,
    retry: false,
  });
}

export function useApproveSyncChangeBatch(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (batchId: string) => (await apiClient.post<SyncChangeBatch>(`/api/sync-change-batches/${batchId}/approve`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sync-change-batches", workspaceId] });
      toast.success("Batch approved and pushed to its source");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not approve this batch")),
  });
}

export function useRejectSyncChangeBatch(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ batchId, reason, restore }: { batchId: string; reason: string | null; restore?: boolean }) =>
      (await apiClient.post<SyncChangeBatch>(`/api/sync-change-batches/${batchId}/reject`, { reason, restore })).data,
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["sync-change-batches", workspaceId] });
      // A restore changes rows' own data, not just the sync queue.
      if (variables.restore) {
        queryClient.invalidateQueries({ queryKey: ["records"] });
        queryClient.invalidateQueries({ queryKey: ["records-page"] });
      }
      toast.success(variables.restore ? "Batch rejected and local edits reverted" : "Batch rejected");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not reject this batch")),
  });
}

export function useUnlinkTableSync(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => apiClient.delete(`/api/tables/${tableId}/sync`),
    onSuccess: () => {
      queryClient.setQueryData(["table-sync", tableId], null);
      toast.success("Sync removed — this table is now independent of its source");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not unlink sync")),
  });
}

export function useRunTableSyncPullNow(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await apiClient.post<TableSyncConfig>(`/api/tables/${tableId}/sync/pull/run-now`)).data,
    onSuccess: (config) => {
      // The pull itself runs on the worker, not inline -- any rows it
      // touches arrive over the table's own live-updates websocket
      // (record_change, see useTableLiveUpdates) once that job actually
      // runs, same as an ordinary poll. Nothing to invalidate here yet.
      queryClient.setQueryData(["table-sync", tableId], config);
      toast.success("Sync started — changes will appear shortly");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not start sync")),
  });
}

export function useConfigurePull(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      externalUpdatedAtColumn: string | null;
      pollIntervalSeconds: number | null;
      deletionCheckIntervalSeconds: number | null;
    }) =>
      (
        await apiClient.patch<TableSyncConfig>(`/api/tables/${tableId}/sync/pull`, {
          external_updated_at_column: payload.externalUpdatedAtColumn,
          poll_interval_seconds: payload.pollIntervalSeconds,
          deletion_check_interval_seconds: payload.deletionCheckIntervalSeconds,
        })
      ).data,
    onSuccess: (config) => {
      queryClient.setQueryData(["table-sync", tableId], config);
      toast.success(config.external_updated_at_column ? "Pulling changes from the source" : "Pull disabled");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not update pull settings")),
  });
}
