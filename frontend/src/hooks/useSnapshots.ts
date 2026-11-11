import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, apiErrorMessage } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import type { Base, BaseSnapshot, RestoreSnapshotResult } from "../types";

export function useSnapshots(baseId: string | undefined) {
  return useQuery({
    queryKey: ["snapshots", baseId],
    queryFn: async () => (await apiClient.get<BaseSnapshot[]>(`/api/bases/${baseId}/snapshots`)).data,
    enabled: !!baseId,
  });
}

export function useCreateSnapshot(baseId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (label: string | null) => (await apiClient.post<BaseSnapshot>(`/api/bases/${baseId}/snapshots`, { label })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["snapshots", baseId] });
      toast.success("Snapshot taken");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not take a snapshot")),
  });
}

export function useDeleteSnapshot(baseId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (snapshotId: string) => apiClient.delete(`/api/snapshots/${snapshotId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["snapshots", baseId] });
      toast.success("Snapshot deleted");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not delete this snapshot")),
  });
}

export function useSetAutoSnapshotsEnabled(baseId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (enabled: boolean) =>
      (await apiClient.patch<Base>(`/api/bases/${baseId}/snapshots/settings`, { auto_snapshots_enabled: enabled })).data,
    onSuccess: (base) => {
      queryClient.setQueryData(["base", baseId], base);
      toast.success(base.auto_snapshots_enabled ? "Automatic daily snapshots turned on" : "Automatic daily snapshots turned off");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not update snapshot settings")),
  });
}

export function usePreviewRestore(snapshotId: string | undefined) {
  return useQuery({
    queryKey: ["snapshot-preview", snapshotId],
    queryFn: async () => (await apiClient.get<RestoreSnapshotResult>(`/api/snapshots/${snapshotId}/preview`)).data,
    enabled: !!snapshotId,
    // Read-only and cheap, but the underlying data can change between
    // opening the confirm dialog and actually clicking Restore -- don't
    // serve a stale preview from cache across separate times it's opened.
    staleTime: 0,
  });
}

export function useRestoreSnapshot(baseId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (snapshotId: string) =>
      (await apiClient.post<RestoreSnapshotResult>(`/api/snapshots/${snapshotId}/restore`)).data,
    onSuccess: () => {
      // The tables restored into live here (records/dashboards/etc) --
      // simplest safe invalidation is everything under this base's tables,
      // rather than trying to enumerate exactly which rows changed.
      queryClient.invalidateQueries({ queryKey: ["tables", baseId] });
      queryClient.invalidateQueries({ queryKey: ["records"] });
      queryClient.invalidateQueries({ queryKey: ["records-page"] });
      toast.success("Restored");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not restore this snapshot")),
  });
}
