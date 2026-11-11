import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import type {
  ActionType,
  Automation,
  AutomationAction,
  AutomationRun,
  AutomationTriggerConfig,
  TriggerType,
} from "../types";

export function useAutomations(tableId: string | undefined) {
  return useQuery({
    queryKey: ["automations", tableId],
    queryFn: async () => (await apiClient.get<Automation[]>(`/api/tables/${tableId}/automations`)).data,
    enabled: !!tableId,
  });
}

export function useCreateAutomation(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { name: string; trigger_type: TriggerType; trigger_config: AutomationTriggerConfig }) =>
      (await apiClient.post<Automation>(`/api/tables/${tableId}/automations`, body)).data,
    onSuccess: (automation) => {
      queryClient.invalidateQueries({ queryKey: ["automations", tableId] });
      toast.success(`Created automation "${automation.name}"`);
    },
  });
}

export function useUpdateAutomation(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: { id: string; name?: string; is_enabled?: boolean; trigger_config?: AutomationTriggerConfig }) =>
      (await apiClient.patch<Automation>(`/api/automations/${id}`, body)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["automations", tableId] }),
  });
}

export function useDeleteAutomation(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => apiClient.delete(`/api/automations/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automations", tableId] });
      toast.success("Automation deleted");
    },
  });
}

export function useAutomationActions(automationId: string | undefined) {
  return useQuery({
    queryKey: ["automation-actions", automationId],
    queryFn: async () => (await apiClient.get<AutomationAction[]>(`/api/automations/${automationId}/actions`)).data,
    enabled: !!automationId,
  });
}

export function useCreateAutomationAction(automationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { action_type: ActionType; config: Record<string, unknown> }) =>
      (await apiClient.post<AutomationAction>(`/api/automations/${automationId}/actions`, body)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation-actions", automationId] });
      toast.success("Action added");
    },
  });
}

export function useDeleteAutomationAction(automationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (actionId: string) => apiClient.delete(`/api/automations/${automationId}/actions/${actionId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation-actions", automationId] });
      toast.success("Action removed");
    },
  });
}

export function useAutomationRuns(automationId: string | undefined) {
  return useQuery({
    queryKey: ["automation-runs", automationId],
    queryFn: async () => (await apiClient.get<AutomationRun[]>(`/api/automations/${automationId}/runs`)).data,
    enabled: !!automationId,
    refetchInterval: 5000,
  });
}
