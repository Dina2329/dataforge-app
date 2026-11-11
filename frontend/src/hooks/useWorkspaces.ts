import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, apiErrorMessage } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import type { Workspace } from "../types";

export function useWorkspaces() {
  return useQuery({
    queryKey: ["workspaces"],
    queryFn: async () => (await apiClient.get<Workspace[]>("/api/workspaces")).data,
  });
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (name: string) => (await apiClient.post<Workspace>("/api/workspaces", { name })).data,
    onSuccess: (workspace) => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      toast.success(`Created workspace "${workspace.name}"`);
    },
  });
}

export function useDeleteWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (workspaceId: string) => apiClient.delete(`/api/workspaces/${workspaceId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      toast.success("Workspace deleted");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not delete workspace")),
  });
}
