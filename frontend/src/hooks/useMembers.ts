import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, apiErrorMessage } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import type { Member, Team, TeamMember, WorkspaceRole } from "../types";

export function useMembers(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["members", workspaceId],
    queryFn: async () => (await apiClient.get<Member[]>(`/api/workspaces/${workspaceId}/members`)).data,
    enabled: !!workspaceId,
  });
}

export function useInviteMember(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ email, role }: { email: string; role: WorkspaceRole }) =>
      (await apiClient.post<Member>(`/api/workspaces/${workspaceId}/members`, { email, role })).data,
    onSuccess: (member) => {
      queryClient.invalidateQueries({ queryKey: ["members", workspaceId] });
      toast.success(`Invited ${member.email}`);
    },
  });
}

export function useUpdateMemberRole(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, role }: { userId: string; role: WorkspaceRole }) =>
      (await apiClient.patch<Member>(`/api/workspaces/${workspaceId}/members/${userId}`, { role })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members", workspaceId] });
      toast.success("Role updated");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not update role")),
  });
}

export function useRemoveMember(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (userId: string) => apiClient.delete(`/api/workspaces/${workspaceId}/members/${userId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members", workspaceId] });
      toast.success("Member removed");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not remove member")),
  });
}

export function useTeams(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["teams", workspaceId],
    queryFn: async () => (await apiClient.get<Team[]>(`/api/workspaces/${workspaceId}/teams`)).data,
    enabled: !!workspaceId,
  });
}

export function useCreateTeam(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (name: string) => (await apiClient.post<Team>(`/api/workspaces/${workspaceId}/teams`, { name })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["teams", workspaceId] }),
  });
}

export function useDeleteTeam(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (teamId: string) => apiClient.delete(`/api/workspaces/${workspaceId}/teams/${teamId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["teams", workspaceId] }),
  });
}

export function useTeamMembers(workspaceId: string | undefined, teamId: string | undefined) {
  return useQuery({
    queryKey: ["team-members", teamId],
    queryFn: async () => (await apiClient.get<TeamMember[]>(`/api/workspaces/${workspaceId}/teams/${teamId}/members`)).data,
    enabled: !!workspaceId && !!teamId,
  });
}

export function useAddTeamMember(workspaceId: string | undefined, teamId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (email: string) => apiClient.post(`/api/workspaces/${workspaceId}/teams/${teamId}/members`, { email }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team-members", teamId] }),
  });
}

export function useRemoveTeamMember(workspaceId: string | undefined, teamId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (userId: string) => apiClient.delete(`/api/workspaces/${workspaceId}/teams/${teamId}/members/${userId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team-members", teamId] }),
  });
}
