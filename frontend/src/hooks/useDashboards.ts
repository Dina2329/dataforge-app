import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import type { Base, Dashboard, PublicDashboard, Table, Widget, WidgetConfig, WidgetData, WidgetPosition, WidgetSourceType, WidgetTypeKey } from "../types";

// No single "all tables in a workspace" endpoint exists (tables are scoped
// per base), so this aggregates across bases client-side — fine at this
// scale; worth promoting to a dedicated backend endpoint if base counts grow.
export function useWorkspaceTables(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["workspace-tables", workspaceId],
    queryFn: async () => {
      const bases = (await apiClient.get<Base[]>(`/api/workspaces/${workspaceId}/bases`)).data;
      const tableLists = await Promise.all(
        bases.map((base) => apiClient.get<Table[]>(`/api/bases/${base.id}/tables`).then((r) => r.data)),
      );
      return tableLists.flat();
    },
    enabled: !!workspaceId,
  });
}

export function useDashboards(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["dashboards", workspaceId],
    queryFn: async () => (await apiClient.get<Dashboard[]>(`/api/workspaces/${workspaceId}/dashboards`)).data,
    enabled: !!workspaceId,
  });
}

export function useCreateDashboard(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (name: string) => (await apiClient.post<Dashboard>(`/api/workspaces/${workspaceId}/dashboards`, { name })).data,
    onSuccess: (dashboard) => {
      queryClient.invalidateQueries({ queryKey: ["dashboards", workspaceId] });
      toast.success(`Created dashboard "${dashboard.name}"`);
    },
  });
}

export function useDashboard(dashboardId: string | undefined) {
  return useQuery({
    queryKey: ["dashboard", dashboardId],
    queryFn: async () => (await apiClient.get<Dashboard>(`/api/dashboards/${dashboardId}`)).data,
    enabled: !!dashboardId,
  });
}

export function useDeleteDashboard(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (dashboardId: string) => apiClient.delete(`/api/dashboards/${dashboardId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboards", workspaceId] });
      toast.success("Dashboard deleted");
    },
  });
}

export function useWidgets(dashboardId: string | undefined) {
  return useQuery({
    queryKey: ["widgets", dashboardId],
    queryFn: async () => (await apiClient.get<Widget[]>(`/api/dashboards/${dashboardId}/widgets`)).data,
    enabled: !!dashboardId,
  });
}

export function useCreateWidget(dashboardId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      name: string;
      widget_type: WidgetTypeKey;
      source_type: WidgetSourceType;
      table_id: string | null;
      config: WidgetConfig;
      position: WidgetPosition;
    }) => (await apiClient.post<Widget>(`/api/dashboards/${dashboardId}/widgets`, payload)).data,
    onSuccess: (widget) => {
      queryClient.invalidateQueries({ queryKey: ["widgets", dashboardId] });
      toast.success(`Added widget "${widget.name}"`);
    },
  });
}

export function useUpdateWidget(dashboardId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ widgetId, position }: { widgetId: string; position: WidgetPosition }) =>
      (await apiClient.patch<Widget>(`/api/dashboards/${dashboardId}/widgets/${widgetId}`, { position })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["widgets", dashboardId] }),
  });
}

export function useDeleteWidget(dashboardId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (widgetId: string) => apiClient.delete(`/api/dashboards/${dashboardId}/widgets/${widgetId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["widgets", dashboardId] }),
  });
}

export function useWidgetData(dashboardId: string | undefined, widgetId: string) {
  return useQuery({
    queryKey: ["widget-data", dashboardId, widgetId],
    queryFn: async () => (await apiClient.get<WidgetData>(`/api/dashboards/${dashboardId}/widgets/${widgetId}/data`)).data,
    enabled: !!dashboardId,
    refetchInterval: 15000,
  });
}

/** Live preview for the Add Widget dialog -- computes real data for a widget
 * that doesn't exist yet (see backend WidgetPreviewRequest), so the dialog
 * never fabricates a chart from placeholder numbers. `enabled` gates on the
 * caller having picked enough config to make a valid query (e.g. an x_field
 * for a bar/line/pie widget) -- an invalid partial config 400s otherwise. */
export function usePreviewWidgetData(params: {
  tableId?: string;
  sourceType: WidgetSourceType;
  workspaceId?: string;
  widgetType: WidgetTypeKey;
  config: WidgetConfig;
  enabled: boolean;
}) {
  const { tableId, sourceType, workspaceId, widgetType, config, enabled } = params;
  return useQuery({
    queryKey: ["widget-preview", sourceType, tableId, workspaceId, widgetType, config],
    queryFn: async () =>
      (
        await apiClient.post<WidgetData>("/api/dashboards/widgets/preview", {
          source_type: sourceType,
          table_id: tableId ?? null,
          workspace_id: workspaceId ?? null,
          widget_type: widgetType,
          config,
        })
      ).data,
    enabled,
  });
}

export function useCreateShareLink(dashboardId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await apiClient.post<Dashboard>(`/api/dashboards/${dashboardId}/share`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard", dashboardId] });
      toast.success("Share link created");
    },
  });
}

export function useRevokeShareLink(dashboardId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await apiClient.delete<Dashboard>(`/api/dashboards/${dashboardId}/share`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard", dashboardId] });
      toast.success("Share link revoked");
    },
  });
}

// Public (no-auth) endpoints backing the shared read-only dashboard view.
export function usePublicDashboard(token: string | undefined) {
  return useQuery({
    queryKey: ["public-dashboard", token],
    queryFn: async () => (await apiClient.get<PublicDashboard>(`/api/public/dashboards/${token}`)).data,
    enabled: !!token,
    retry: false,
  });
}

export function usePublicWidgets(token: string | undefined) {
  return useQuery({
    queryKey: ["public-widgets", token],
    queryFn: async () => (await apiClient.get<Widget[]>(`/api/public/dashboards/${token}/widgets`)).data,
    enabled: !!token,
  });
}

export function usePublicWidgetData(token: string | undefined, widgetId: string) {
  return useQuery({
    queryKey: ["public-widget-data", token, widgetId],
    queryFn: async () => (await apiClient.get<WidgetData>(`/api/public/dashboards/${token}/widgets/${widgetId}/data`)).data,
    enabled: !!token,
    refetchInterval: 15000,
  });
}
