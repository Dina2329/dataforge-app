import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, apiErrorMessage } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import type { Base, ExcelImportResult, ExcelSheetPreview, Table, View, ViewType } from "../types";

export function useBases(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["bases", workspaceId],
    queryFn: async () => (await apiClient.get<Base[]>(`/api/workspaces/${workspaceId}/bases`)).data,
    enabled: !!workspaceId,
  });
}

export function useCreateBase(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (name: string) =>
      (await apiClient.post<Base>(`/api/workspaces/${workspaceId}/bases`, { name })).data,
    onSuccess: (base) => {
      queryClient.invalidateQueries({ queryKey: ["bases", workspaceId] });
      toast.success(`Created base "${base.name}"`);
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not create base")),
  });
}

export function useDeleteBase(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (baseId: string) => apiClient.delete(`/api/bases/${baseId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bases", workspaceId] });
      toast.success("Base deleted");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not delete base")),
  });
}

export function useTables(baseId: string | undefined) {
  return useQuery({
    queryKey: ["tables", baseId],
    queryFn: async () => (await apiClient.get<Table[]>(`/api/bases/${baseId}/tables`)).data,
    enabled: !!baseId,
  });
}

export function useCreateTable(baseId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (name: string) => (await apiClient.post<Table>(`/api/bases/${baseId}/tables`, { name })).data,
    onSuccess: (table) => {
      queryClient.invalidateQueries({ queryKey: ["tables", baseId] });
      toast.success(`Created table "${table.name}"`);
    },
  });
}

export function useDeleteTable(baseId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (tableId: string) => apiClient.delete(`/api/tables/${tableId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tables", baseId] });
      toast.success("Table deleted");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not delete table")),
  });
}

export function useImportCsv(baseId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ tableName, file }: { tableName: string; file: File }) => {
      const form = new FormData();
      form.append("table_name", tableName);
      form.append("file", file);
      const { data } = await apiClient.post<Table>(`/api/bases/${baseId}/import-csv`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
    onSuccess: (table) => {
      queryClient.invalidateQueries({ queryKey: ["tables", baseId] });
      toast.success(`Imported CSV into "${table.name}"`);
    },
  });
}

export function useInspectExcel(baseId: string | undefined) {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const { data } = await apiClient.post<{ sheets: ExcelSheetPreview[] }>(`/api/bases/${baseId}/import-excel/inspect`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data.sheets;
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not read that Excel file")),
  });
}

export function useImportExcel(baseId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, sheets }: { file: File; sheets: { sheet_name: string; table_name: string }[] }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("sheets", JSON.stringify(sheets));
      const { data } = await apiClient.post<{ results: ExcelImportResult[] }>(`/api/bases/${baseId}/import-excel`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data.results;
    },
    onSuccess: (results) => {
      queryClient.invalidateQueries({ queryKey: ["tables", baseId] });
      const succeeded = results.filter((r) => r.table).length;
      const failed = results.length - succeeded;
      if (succeeded > 0) toast.success(`Imported ${succeeded} sheet${succeeded === 1 ? "" : "s"} as table${succeeded === 1 ? "" : "s"}`);
      if (failed > 0) toast.error(`${failed} sheet${failed === 1 ? "" : "s"} failed to import`);
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not import Excel file")),
  });
}

export function useTable(tableId: string | undefined) {
  return useQuery({
    queryKey: ["table", tableId],
    queryFn: async () => (await apiClient.get<Table>(`/api/tables/${tableId}`)).data,
    enabled: !!tableId,
  });
}

export function useCreateField(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; field_type: string; options?: object; required?: boolean }) =>
      (await apiClient.post(`/api/tables/${tableId}/fields`, payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["table", tableId] }),
  });
}

export function useUpdateField(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ fieldId, ...payload }: { fieldId: string; name?: string; required?: boolean; options?: object }) =>
      (await apiClient.patch(`/api/tables/${tableId}/fields/${fieldId}`, payload)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["table", tableId] });
      toast.success("Field updated");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not update field")),
  });
}

export function useDeleteField(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (fieldId: string) => apiClient.delete(`/api/tables/${tableId}/fields/${fieldId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["table", tableId] });
      toast.success("Field deleted");
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not delete field")),
  });
}

export function useCreateView(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; view_type: ViewType; config?: Record<string, unknown> }) =>
      (await apiClient.post<View>(`/api/tables/${tableId}/views`, payload)).data,
    onSuccess: (view) => {
      queryClient.invalidateQueries({ queryKey: ["table", tableId] });
      toast.success(`Created view "${view.name}"`);
    },
  });
}

export function useUpdateView(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ viewId, ...payload }: { viewId: string; name?: string; config?: Record<string, unknown> }) =>
      (await apiClient.patch<View>(`/api/tables/${tableId}/views/${viewId}`, payload)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["table", tableId] }),
  });
}

export function useDeleteView(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (viewId: string) => apiClient.delete(`/api/tables/${tableId}/views/${viewId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["table", tableId] });
      toast.success("View deleted");
    },
  });
}

export function useCreateViewShareLink(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (viewId: string) => (await apiClient.post<View>(`/api/tables/${tableId}/views/${viewId}/share`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["table", tableId] });
      toast.success("Share link created");
    },
  });
}

export function useRevokeViewShareLink(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (viewId: string) => (await apiClient.delete<View>(`/api/tables/${tableId}/views/${viewId}/share`)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["table", tableId] });
      toast.success("Share link revoked");
    },
  });
}

export function useExportBase() {
  return useMutation({
    mutationFn: async ({ baseId, baseName }: { baseId: string; baseName: string }) => {
      const response = await apiClient.get(`/api/bases/${baseId}/export`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${baseName.replace(/[^a-zA-Z0-9 _-]/g, "_")}.json`;
      link.click();
      URL.revokeObjectURL(url);
    },
  });
}

export function useImportBase(workspaceId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const text = await file.text();
      const data = JSON.parse(text);
      return (await apiClient.post<Base>(`/api/workspaces/${workspaceId}/bases/import`, data)).data;
    },
    onSuccess: (base) => {
      queryClient.invalidateQueries({ queryKey: ["bases", workspaceId] });
      toast.success(`Imported base "${base.name}"`);
    },
  });
}
