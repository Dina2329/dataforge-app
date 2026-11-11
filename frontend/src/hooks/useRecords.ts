import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
} from "@tanstack/react-query";
import { apiClient, apiErrorMessage } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import type { FilterExpr, RecordListResponse, RecordRow, ViewSort } from "../types";

const PAGE_SIZE = 200;

// Two different cache shapes hold a table's rows: ["records", ...] is the
// infinite-scroll accumulator useRecords still backs the Kanban/Form views
// with, and ["records-page", ...] is the single-page-at-a-time cache
// usePagedRecords backs the grid view with (see its own docstring for why
// these are separate instead of one hook serving both). Every write needs to
// keep both in sync, or whichever view isn't currently open goes stale.
export function invalidateRecordsQueries(queryClient: QueryClient, tableId: string | undefined) {
  queryClient.invalidateQueries({ queryKey: ["records", tableId] });
  queryClient.invalidateQueries({ queryKey: ["records-page", tableId] });
}

// Rewrites one row across every cached records page for this table (every
// sort/filter/cursor variant -- the partial queryKey match covers all of
// them, in both cache shapes), so a cell edit updates in place instead of
// needing a network refetch to see its own result.
function patchRowInCache(
  queryClient: QueryClient,
  tableId: string | undefined,
  rowId: number,
  updater: (row: RecordRow) => RecordRow,
) {
  queryClient.setQueriesData<InfiniteData<RecordListResponse>>({ queryKey: ["records", tableId] }, (old) => {
    if (!old) return old;
    return { ...old, pages: old.pages.map((page) => ({ ...page, rows: page.rows.map((r) => (r.row_id === rowId ? updater(r) : r)) })) };
  });
  queryClient.setQueriesData<RecordListResponse>({ queryKey: ["records-page", tableId] }, (old) => {
    if (!old) return old;
    return { ...old, rows: old.rows.map((r) => (r.row_id === rowId ? updater(r) : r)) };
  });
}

export function useRecords(tableId: string | undefined, sort?: ViewSort[], filter?: FilterExpr) {
  const sortKey = sort && sort.length ? JSON.stringify(sort) : undefined;
  const filterKey = filter ? JSON.stringify(filter) : undefined;
  return useInfiniteQuery({
    queryKey: ["records", tableId, sortKey, filterKey],
    queryFn: async ({ pageParam }: { pageParam: string | null }) => {
      const { data } = await apiClient.get<RecordListResponse>(`/api/tables/${tableId}/rows`, {
        params: {
          limit: PAGE_SIZE,
          cursor: pageParam ?? undefined,
          sort: sortKey,
          filter: filterKey,
        },
      });
      return data;
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => (lastPage.has_more ? lastPage.next_cursor : undefined),
    enabled: !!tableId,
  });
}

// One page at a time, navigated with Previous/Next rather than accumulated
// by scrolling -- the grid view's own query, kept separate from useRecords
// (which still backs Kanban/Form views unchanged) specifically so switching
// the grid to paged navigation doesn't also cap what Kanban/Form can see to
// whatever page happens to be cached. `cursor` is owned by the caller (see
// TableGridPage's pageCursor/cursorHistory) since keyset pagination has no
// "page N" of its own to ask the server for -- only "next after this
// cursor," so going back means replaying a cursor the caller already saw.
export function usePagedRecords(tableId: string | undefined, cursor: string | null, sort?: ViewSort[], filter?: FilterExpr) {
  const sortKey = sort && sort.length ? JSON.stringify(sort) : undefined;
  const filterKey = filter ? JSON.stringify(filter) : undefined;
  return useQuery({
    queryKey: ["records-page", tableId, sortKey, filterKey, cursor],
    queryFn: async () => {
      const { data } = await apiClient.get<RecordListResponse>(`/api/tables/${tableId}/rows`, {
        params: { limit: PAGE_SIZE, cursor: cursor ?? undefined, sort: sortKey, filter: filterKey },
      });
      return data;
    },
    enabled: !!tableId,
    // Keeps showing the page you're leaving while the next one loads,
    // instead of flashing to a blank/loading grid on every Next/Previous
    // click.
    placeholderData: keepPreviousData,
  });
}

export function useCreateRecord(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (values: Record<string, unknown>) =>
      (await apiClient.post<RecordRow>(`/api/tables/${tableId}/rows`, { values })).data,
    onSuccess: () => invalidateRecordsQueries(queryClient, tableId),
  });
}

export function useUpdateRecord(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      rowId,
      values,
      expectedVersion,
    }: {
      rowId: number;
      values: Record<string, unknown>;
      expectedVersion: number;
    }) =>
      (
        await apiClient.patch<RecordRow>(`/api/tables/${tableId}/rows/${rowId}`, {
          values,
          expected_version: expectedVersion,
        })
      ).data,
    // A checkbox (or any cell) previously only visually changed once the
    // PATCH resolved AND a full requery of every loaded page came back --
    // slow, and a second click before that finished reused the same
    // now-stale expectedVersion, 409ing silently (no onError existed) and
    // leaving the cell looking like it "didn't take" or bounced back. This
    // updates the cell instantly from the edit itself, rolls back cleanly on
    // a real failure (with a visible reason), and folds the server's own
    // response back in on success instead of triggering a fresh refetch.
    onMutate: async ({ rowId, values }) => {
      await queryClient.cancelQueries({ queryKey: ["records", tableId] });
      await queryClient.cancelQueries({ queryKey: ["records-page", tableId] });
      const previous = [
        ...queryClient.getQueriesData<InfiniteData<RecordListResponse>>({ queryKey: ["records", tableId] }),
        ...queryClient.getQueriesData<RecordListResponse>({ queryKey: ["records-page", tableId] }),
      ];
      patchRowInCache(queryClient, tableId, rowId, (row) => ({ ...row, values: { ...row.values, ...values }, version: row.version + 1 }));
      return { previous };
    },
    onError: (err, _vars, context) => {
      context?.previous.forEach(([key, data]) => queryClient.setQueryData(key, data));
      toast.error(apiErrorMessage(err, "Could not save change — reload and try again"));
    },
    onSuccess: (updatedRow) => patchRowInCache(queryClient, tableId, updatedRow.row_id, () => updatedRow),
  });
}

export function useDeleteRecord(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (rowId: number) => apiClient.delete(`/api/tables/${tableId}/rows/${rowId}`),
    onSuccess: () => invalidateRecordsQueries(queryClient, tableId),
  });
}

export function useUploadAttachment(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ rowId, fieldId, file }: { rowId: number; fieldId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      const { data } = await apiClient.post<RecordRow>(
        `/api/tables/${tableId}/rows/${rowId}/fields/${fieldId}/attachments`,
        form,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      return data;
    },
    onSuccess: () => invalidateRecordsQueries(queryClient, tableId),
    onError: (err) => toast.error(apiErrorMessage(err, "Could not upload file")),
  });
}

export function useDeleteAttachment(tableId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ rowId, fieldId, attachmentId }: { rowId: number; fieldId: string; attachmentId: string }) =>
      (await apiClient.delete<RecordRow>(`/api/tables/${tableId}/rows/${rowId}/fields/${fieldId}/attachments/${attachmentId}`))
        .data,
    onSuccess: () => invalidateRecordsQueries(queryClient, tableId),
  });
}

export function useDownloadAttachment(tableId: string | undefined) {
  return useMutation({
    mutationFn: async ({
      rowId,
      fieldId,
      attachmentId,
      filename,
    }: {
      rowId: number;
      fieldId: string;
      attachmentId: string;
      filename: string;
    }) => {
      const response = await apiClient.get(
        `/api/tables/${tableId}/rows/${rowId}/fields/${fieldId}/attachments/${attachmentId}/download`,
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    },
  });
}

export function useExportCsv(tableId: string | undefined, tableName: string, sort?: ViewSort[], filter?: FilterExpr) {
  return useMutation({
    mutationFn: async () => {
      const response = await apiClient.get(`/api/tables/${tableId}/export-csv`, {
        responseType: "blob",
        params: {
          sort: sort && sort.length ? JSON.stringify(sort) : undefined,
          filter: filter ? JSON.stringify(filter) : undefined,
        },
      });
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${tableName}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    },
    onError: (err) => toast.error(apiErrorMessage(err, "Could not export CSV")),
  });
}
