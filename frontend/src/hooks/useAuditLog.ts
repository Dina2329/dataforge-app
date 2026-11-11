import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../lib/apiClient";
import type { AuditLogEntry } from "../types";

export function useAuditLog(workspaceId: string | undefined, resourceType: string | undefined) {
  return useQuery({
    queryKey: ["audit-log", workspaceId, resourceType],
    queryFn: async () =>
      (
        await apiClient.get<AuditLogEntry[]>(`/api/workspaces/${workspaceId}/audit-log`, {
          params: resourceType ? { resource_type: resourceType } : undefined,
        })
      ).data,
    enabled: !!workspaceId,
  });
}
