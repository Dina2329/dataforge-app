import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  Filter,
  FolderOutput,
  ListChecks,
  MoreHorizontal,
  Plus,
  Rows3,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Table2,
  Trash2,
  WrapText,
  X,
  Zap,
} from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useDeleteField, useTable, useUpdateView } from "../hooks/useBases";
import { useBase } from "../hooks/useDataSources";
import {
  useCreateRecord,
  useDeleteRecord,
  useExportCsv,
  usePagedRecords,
  useRecords,
  useUpdateRecord,
} from "../hooks/useRecords";
import { useRecordSubmitConfig, useSubmitRow } from "../hooks/useRecordSubmit";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import { useTableLiveUpdates } from "../hooks/useTableLiveUpdates";
import {
  DENSITY_ROW_HEIGHT,
  GRID_DENSITIES,
  useGridDensity,
  useGridWrapText,
} from "../hooks/useGridDensity";
import { rowMatchesSearch } from "../lib/searchRow";
import { setColumnFilterValues } from "../lib/filterHelpers";
import { DataGrid } from "../components/grid/DataGrid";
import { KanbanBoard } from "../components/grid/KanbanBoard";
import { FormViewPanel } from "../components/grid/FormViewPanel";
import { ViewTabs } from "../components/grid/ViewTabs";
import { AddColumnDialog } from "../components/grid/AddColumnDialog";
import { TableSyncStatus } from "../components/connectors/TableSyncStatus";
import { EditColumnDialog } from "../components/grid/EditColumnDialog";
import { GridFilterDialog } from "../components/grid/GridFilterDialog";
import { RowDetailDialog } from "../components/grid/RowDetailDialog";
import { BulkUpdateDialog } from "../components/bulk/BulkUpdateDialog";
import { RowPoliciesDialog } from "../components/grid/RowPoliciesDialog";
import { SubmitConfigDialog } from "../components/grid/SubmitConfigDialog";
import { BatchSubmitConfigDialog } from "../components/grid/BatchSubmitConfigDialog";
import { BatchSubmitDialog } from "../components/grid/BatchSubmitDialog";
import { MissingTermsConfigDialog } from "../components/grid/MissingTermsConfigDialog";
import { MissingTermsPanel } from "../components/grid/MissingTermsPanel";
import { JobsPanel } from "../components/grid/JobsPanel";
import { JobResultsDialog } from "../components/grid/JobResultsDialog";
import { GroupCleanupDialog } from "../components/grid/GroupCleanupDialog";
import { ConfirmDeleteDialog } from "../components/shared/ConfirmDeleteDialog";
import { Avatar } from "../components/ui/Avatar";
import { Button } from "../components/ui/Button";
import { DropdownItem, DropdownMenu } from "../components/ui/DropdownMenu";
import { PageSpinner } from "../components/shared/PageSpinner";
import { toast } from "../stores/toastStore";
import type { Field, FilterExpr, RecordRow } from "../types";

const UNDO_STACK_LIMIT = 20;

const DENSITY_LABELS: Record<(typeof GRID_DENSITIES)[number], string> = {
  compact: "Compact",
  comfortable: "Comfortable",
  spacious: "Spacious",
};

export function TableGridPage() {
  const { tableId } = useParams<{ tableId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: table, isLoading: tableLoading } = useTable(tableId);
  const { data: base } = useBase(table?.base_id);
  useReportWorkspaceContext(base?.workspace_id);
  const { activeUsers, focusedCells, sendCellFocus } =
    useTableLiveUpdates(tableId);
  const [density, setDensity] = useGridDensity();
  const [wrapText, setWrapText] = useGridWrapText();
  const createRecord = useCreateRecord(tableId);
  const updateRecord = useUpdateRecord(tableId);
  const deleteRecord = useDeleteRecord(tableId);
  const { data: submitConfig } = useRecordSubmitConfig(tableId);
  const submitRow = useSubmitRow(tableId);
  const updateView = useUpdateView(tableId);
  const deleteField = useDeleteField(tableId);

  const [addColumnOpen, setAddColumnOpen] = useState(false);
  const [editFieldTarget, setEditFieldTarget] = useState<Field | null>(null);
  const [deleteFieldTarget, setDeleteFieldTarget] = useState<Field | null>(
    null,
  );
  const [bulkUpdateOpen, setBulkUpdateOpen] = useState(false);
  const [rowPoliciesOpen, setRowPoliciesOpen] = useState(false);
  const [submitConfigOpen, setSubmitConfigOpen] = useState(false);
  const [batchSubmitConfigOpen, setBatchSubmitConfigOpen] = useState(false);
  const [batchSubmitOpen, setBatchSubmitOpen] = useState(false);
  const [missingTermsConfigOpen, setMissingTermsConfigOpen] = useState(false);
  const [groupCleanupOpen, setGroupCleanupOpen] = useState(false);
  const [missingTermsOpen, setMissingTermsOpen] = useState(false);
  const [missingTermsCollapsed, setMissingTermsCollapsed] = useState(false);
  const [jobResultsJobId, setJobResultsJobId] = useState<string | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [expandedRowId, setExpandedRowId] = useState<number | null>(null);
  const [activeViewId, setActiveViewId] = useState<string | undefined>(
    undefined,
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [deleteRowTarget, setDeleteRowTarget] = useState<RecordRow | null>(
    null,
  );
  const [selectedRowIds, setSelectedRowIds] = useState<Set<number>>(new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [flashRowId, setFlashRowId] = useState<number | null>(null);
  // Grid view pages with Previous/Next instead of accumulating by scrolling
  // (see usePagedRecords) -- keyset pagination has no "page N" to ask the
  // server for, so going back means replaying a cursor already seen, which
  // this stack tracks. null = first page.
  const [pageCursor, setPageCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([]);
  // Ctrl/Cmd+Z undo for single-cell edits, mirroring real spreadsheets --
  // a ref (not state) since pushing to it shouldn't itself trigger a
  // re-render, and the keydown listener below needs a stable callback.
  const undoStackRef = useRef<
    { rowId: number; fieldName: string; previousValue: unknown }[]
  >([]);
  const rowsRef = useRef<RecordRow[]>([]);

  function performUndo() {
    const entry = undoStackRef.current.pop();
    if (!entry) return;
    const currentRow = rowsRef.current.find((r) => r.row_id === entry.rowId);
    if (!currentRow) return;
    updateRecord.mutate(
      {
        rowId: entry.rowId,
        values: { [entry.fieldName]: entry.previousValue },
        expectedVersion: currentRow.version,
      },
      { onSuccess: () => toast.info(`Reverted "${entry.fieldName}"`) },
    );
  }

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      // Scoped to "focus is somewhere inside the grid" (a cell wrapper, or the
      // input a click just opened inside one -- GridCell opens its editor on
      // a plain click, so a freshly-focused input is the normal post-click
      // state here, not evidence of real in-progress typing worth preserving
      // native undo for). Elsewhere on the page -- the search box, a dialog's
      // field -- this must stay hands-off so their own native undo still works.
      const active = document.activeElement;
      if (!active?.closest("[data-cell]")) return;
      e.preventDefault();
      performUndo();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleCreateRow() {
    createRecord.mutate(
      {},
      {
        onSuccess: (row) => {
          setFlashRowId(row.row_id);
          setTimeout(
            () =>
              setFlashRowId((current) =>
                current === row.row_id ? null : current,
              ),
            1300,
          );
        },
      },
    );
  }

  useEffect(() => {
    setSearchQuery("");
    setSelectedRowIds(new Set());
  }, [tableId]);

  function resetPagination() {
    setPageCursor(null);
    setCursorHistory([]);
  }

  const activeView =
    table?.views.find((v) => v.id === activeViewId) ?? table?.views[0];
  const sort =
    activeView?.view_type === "grid" ? activeView.config.sort : undefined;
  const filter =
    activeView?.view_type === "grid" ? activeView.config.filter : undefined;
  const columnOrder =
    activeView?.view_type === "grid"
      ? activeView.config.column_order
      : undefined;
  const columnWidths =
    activeView?.view_type === "grid"
      ? activeView.config.column_widths
      : undefined;
  const filterCount = !filter
    ? 0
    : filter.kind === "group"
      ? filter.items.length
      : 1;

  // A dashboard drill-down (click a bar/pie segment) arrives as URL params
  // rather than being written into the view's own saved filter -- it's a
  // one-off "show me just this" for whoever clicked, not a change to what
  // everyone else sees on this view. ANDed onto the view's filter (if any)
  // rather than replacing it, so drilling down still respects the view's
  // own scoping.
  const missingTermsJobParam = searchParams.get("missingTermsJob") ?? undefined;
  const drillField = searchParams.get("filterField");
  const drillValue = searchParams.get("filterValue");
  const drillFilter: FilterExpr | undefined =
    drillField && drillValue !== null
      ? {
          kind: "condition",
          field: drillField,
          operator: "eq",
          value: drillValue,
        }
      : undefined;
  const effectiveFilter: FilterExpr | undefined = drillFilter
    ? filter
      ? { kind: "group", logic: "and", items: [filter, drillFilter] }
      : drillFilter
    : filter;

  // Kanban/Form keep the old infinite accumulator (unchanged -- Kanban needs
  // every row to group correctly by status, not one page at a time); only
  // the grid view paginates. Each hook is disabled (tableId -> undefined)
  // for the view type it doesn't serve, so switching views never fires both
  // queries for the same data.
  const isGridView = !activeView || activeView.view_type === "grid";
  const recordsQuery = useRecords(
    isGridView ? undefined : tableId,
    sort,
    effectiveFilter,
  );
  const pagedQuery = usePagedRecords(
    isGridView ? tableId : undefined,
    pageCursor,
    sort,
    effectiveFilter,
  );
  const exportCsv = useExportCsv(
    tableId,
    table?.name ?? "table",
    sort,
    effectiveFilter,
  );

  const sortKey = sort && sort.length ? JSON.stringify(sort) : undefined;
  const filterKey = effectiveFilter
    ? JSON.stringify(effectiveFilter)
    : undefined;
  useEffect(() => {
    resetPagination();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tableId, sortKey, filterKey]);

  // Opened from a Missing Terms job's notification link -- jump straight
  // into that job's results instead of making the user find it in the Jobs panel.
  useEffect(() => {
    if (missingTermsJobParam) setJobResultsJobId(missingTermsJobParam);
  }, [missingTermsJobParam]);

  function clearDrillDown() {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("filterField");
      next.delete("filterValue");
      return next;
    });
  }

  const rows = useMemo(
    () =>
      isGridView
        ? (pagedQuery.data?.rows ?? [])
        : (recordsQuery.data?.pages.flatMap((page) => page.rows) ?? []),
    [isGridView, pagedQuery.data, recordsQuery.data],
  );
  rowsRef.current = rows;

  function handleNextPage() {
    if (!pagedQuery.data?.has_more || !pagedQuery.data.next_cursor) return;
    setCursorHistory((prev) => [...prev, pageCursor]);
    setPageCursor(pagedQuery.data.next_cursor);
  }

  function handlePrevPage() {
    if (cursorHistory.length === 0) return;
    setPageCursor(cursorHistory[cursorHistory.length - 1]);
    setCursorHistory((prev) => prev.slice(0, -1));
  }

  if (tableLoading || !table) {
    return <PageSpinner />;
  }

  const fields: Field[] = [...table.fields].sort(
    (a, b) => a.position - b.position,
  );
  const groupField =
    activeView?.view_type === "kanban"
      ? fields.find((f) => f.id === activeView.config.group_field_id)
      : undefined;
  const primaryField = fields.find((f) => f.is_primary);

  const gridFields = columnOrder
    ? [...fields].sort((a, b) => {
        const ai = columnOrder.indexOf(a.id);
        const bi = columnOrder.indexOf(b.id);
        if (ai === -1 && bi === -1) return a.position - b.position;
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      })
    : fields;

  const displayRows = searchQuery
    ? rows.filter((row) => rowMatchesSearch(row, fields, searchQuery))
    : rows;

  function handleCellCommit(row: RecordRow, field: Field, value: unknown) {
    const previousValue = row.values[field.name];
    if (previousValue !== value) {
      undoStackRef.current.push({
        rowId: row.row_id,
        fieldName: field.name,
        previousValue,
      });
      if (undoStackRef.current.length > UNDO_STACK_LIMIT)
        undoStackRef.current.shift();
    }
    updateRecord.mutate({
      rowId: row.row_id,
      values: { [field.name]: value },
      expectedVersion: row.version,
    });
  }

  function handleDeleteRow(row: RecordRow) {
    setDeleteRowTarget(row);
  }

  function confirmDeleteRow() {
    if (!deleteRowTarget) return;
    deleteRecord.mutate(deleteRowTarget.row_id);
    setDeleteRowTarget(null);
  }

  function confirmDeleteField() {
    if (!deleteFieldTarget) return;
    deleteField.mutate(deleteFieldTarget.id);
    setDeleteFieldTarget(null);
  }

  function toggleRowSelected(rowId: number) {
    setSelectedRowIds((prev) => {
      const next = new Set(prev);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelectedRowIds((prev) =>
      prev.size === displayRows.length
        ? new Set()
        : new Set(displayRows.map((r) => r.row_id)),
    );
  }

  async function confirmBulkDelete() {
    setBulkDeleting(true);
    try {
      await Promise.all(
        [...selectedRowIds].map((rowId) => deleteRecord.mutateAsync(rowId)),
      );
      setSelectedRowIds(new Set());
      setBulkDeleteOpen(false);
    } finally {
      setBulkDeleting(false);
    }
  }

  function handleMoveCard(
    row: RecordRow,
    field: Field,
    newValue: string | null,
  ) {
    updateRecord.mutate({
      rowId: row.row_id,
      values: { [field.name]: newValue },
      expectedVersion: row.version,
    });
  }

  function handleSortChange(fieldName: string, additive: boolean) {
    if (!activeView) return;
    const current = sort ?? [];
    const existingIndex = current.findIndex((s) => s.field === fieldName);

    let next: typeof sort;
    if (!additive) {
      // Plain click: this column becomes the only sort, cycling asc -> desc -> none.
      const existing = existingIndex >= 0 ? current[existingIndex] : undefined;
      next =
        !existing || current.length > 1
          ? [{ field: fieldName, direction: "asc" }]
          : existing.direction === "asc"
            ? [{ field: fieldName, direction: "desc" }]
            : undefined;
    } else {
      // Shift-click: add/cycle this column as an additional sort criterion,
      // keeping every other column's priority order intact.
      if (existingIndex === -1) {
        next = [...current, { field: fieldName, direction: "asc" }];
      } else if (current[existingIndex].direction === "asc") {
        next = current.map((s, i) =>
          i === existingIndex ? { ...s, direction: "desc" } : s,
        );
      } else {
        next = current.filter((_, i) => i !== existingIndex);
      }
    }
    updateView.mutate({
      viewId: activeView.id,
      config: { ...activeView.config, sort: next },
    });
  }

  function handleColumnWidthChange(fieldId: string, width: number) {
    if (!activeView) return;
    const column_widths = {
      ...(activeView.config.column_widths ?? {}),
      [fieldId]: width,
    };
    updateView.mutate({
      viewId: activeView.id,
      config: { ...activeView.config, column_widths },
    });
  }

  function handleReorderColumns(draggedFieldId: string, targetFieldId: string) {
    if (!activeView) return;
    const order = gridFields.map((f) => f.id);
    const fromIndex = order.indexOf(draggedFieldId);
    const toIndex = order.indexOf(targetFieldId);
    if (fromIndex === -1 || toIndex === -1) return;
    order.splice(fromIndex, 1);
    order.splice(toIndex, 0, draggedFieldId);
    updateView.mutate({
      viewId: activeView.id,
      config: { ...activeView.config, column_order: order },
    });
  }

  function handleColumnFilterChange(
    fieldName: string,
    values: unknown[] | null,
  ) {
    if (!activeView) return;
    // Operates on the view's own saved filter, never effectiveFilter -- a
    // dashboard drill-down is a URL-only overlay (see effectiveFilter above)
    // and must never get written back into the view's persisted config.
    const nextFilter = setColumnFilterValues(filter, fieldName, values);
    updateView.mutate({
      viewId: activeView.id,
      config: { ...activeView.config, filter: nextFilter },
    });
  }

  return (
    <div className="flex h-full flex-col p-6">
      {/* A fixed route, not navigate(-1) -- browser history back lands wherever
         the user happened to come from (Automations, Row access, a direct
         link, ...), which reads as "Back" teleporting somewhere unrelated.
         This is a breadcrumb, not an undo -- it always goes to this table's
         own base. */}
      <button
        type="button"
        onClick={() => navigate(`/bases/${table.base_id}`)}
        className="mb-2 inline-flex w-fit items-center gap-1 text-xs text-ink-tertiary hover:text-ink-secondary"
      >
        <ArrowLeft className="size-3" /> Back
      </button>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-y-2">
        <div className="flex shrink-0 items-center gap-2.5">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent-secondary-tint">
            <Table2 className="size-4 text-accent-secondary" />
          </div>
          <h1 className="text-xl font-semibold text-ink-primary">
            {table.name}
          </h1>
          {activeUsers.length > 0 && (
            <div
              className="ml-1 flex items-center -space-x-1.5"
              title={activeUsers.map((u) => u.name || u.email).join(", ")}
            >
              {activeUsers.slice(0, 4).map((u) => (
                <span
                  key={u.user_id}
                  className="rounded-full ring-2 ring-surface"
                >
                  <Avatar name={u.name || u.email} size="sm" />
                </span>
              ))}
              {activeUsers.length > 4 && (
                <span className="flex size-6 items-center justify-center rounded-full bg-surface-raised text-[10px] font-semibold text-ink-secondary ring-2 ring-surface">
                  +{activeUsers.length - 4}
                </span>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {activeView?.view_type !== "form" && (
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-tertiary" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search rows…"
                className="w-40 rounded-lg border border-border-default bg-surface py-2 pl-8 pr-2.5 text-sm text-ink-primary outline-none transition-colors focus:border-accent-secondary focus:ring-2 focus:ring-accent-secondary/30"
              />
            </div>
          )}
          {activeView?.view_type === "grid" && (
            <DropdownMenu
              trigger={<Rows3 className="size-4 text-ink-secondary" />}
            >
              {GRID_DENSITIES.map((d) => (
                <DropdownItem key={d} onClick={() => setDensity(d)}>
                  <span className="flex w-4 justify-center">
                    {d === density && <Check className="size-3.5" />}
                  </span>
                  {DENSITY_LABELS[d]}
                </DropdownItem>
              ))}
            </DropdownMenu>
          )}
          {activeView?.view_type === "grid" && (
            <button
              type="button"
              onClick={() => setWrapText(!wrapText)}
              title={wrapText ? "Turn off text wrap" : "Wrap long cell text"}
              className={`rounded-md p-1.5 transition-colors hover:bg-surface-raised ${wrapText ? "text-accent-secondary" : "text-ink-secondary"}`}
            >
              <WrapText className="size-4" />
            </button>
          )}
          <Button variant="secondary" onClick={() => setAddColumnOpen(true)}>
            <Plus className="size-4" /> Field
          </Button>
          {activeView?.view_type === "grid" && (
            <Button variant="secondary" onClick={() => setFilterOpen(true)}>
              <Filter className="size-4" /> Filter
              {filterCount > 0 ? ` (${filterCount})` : ""}
            </Button>
          )}
          <DropdownMenu
            trigger={
              <span className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-ink-primary ring-1 ring-inset ring-border-strong">
                <MoreHorizontal className="size-4" /> More
              </span>
            }
          >
            <DropdownItem onClick={() => setBulkUpdateOpen(true)}>
              <SlidersHorizontal className="size-4" /> Bulk update
            </DropdownItem>
            <DropdownItem
              onClick={() => navigate(`/tables/${tableId}/automations`)}
            >
              <Zap className="size-4" /> Automations
            </DropdownItem>
            <DropdownItem onClick={() => setRowPoliciesOpen(true)}>
              <ShieldCheck className="size-4" /> Row access
            </DropdownItem>
            {activeView?.view_type === "grid" && (
              <DropdownItem onClick={() => setSubmitConfigOpen(true)}>
                <Send className="size-4" /> Submit settings
              </DropdownItem>
            )}
            {activeView?.view_type === "grid" && (
              <DropdownItem onClick={() => setBatchSubmitConfigOpen(true)}>
                <Send className="size-4" /> Batch Submit config
              </DropdownItem>
            )}
            {activeView?.view_type === "grid" && (
              <DropdownItem onClick={() => setMissingTermsConfigOpen(true)}>
                <ListChecks className="size-4" /> Missing Terms config
              </DropdownItem>
            )}
            {activeView?.view_type === "grid" && (
              <DropdownItem onClick={() => setGroupCleanupOpen(true)}>
                <FolderOutput className="size-4" /> Move to missing term
              </DropdownItem>
            )}
            <DropdownItem
              disabled={exportCsv.isPending}
              onClick={() => exportCsv.mutate()}
            >
              <Download className="size-4" />{" "}
              {exportCsv.isPending ? "Exporting…" : "Export CSV"}
            </DropdownItem>
          </DropdownMenu>
          {activeView?.view_type === "grid" && (
            <Button
              variant="secondary"
              onClick={() => {
                setMissingTermsOpen(true);
                setMissingTermsCollapsed(false);
              }}
            >
              <ListChecks className="size-4" /> Missing Terms
            </Button>
          )}
          {activeView?.view_type === "grid" && (
            <Button variant="secondary" onClick={() => setBatchSubmitOpen(true)}>
              <Send className="size-4" /> Send batch to API
            </Button>
          )}
          {activeView?.view_type === "grid" && tableId && (
            <JobsPanel tableId={tableId} onViewResults={setJobResultsJobId} />
          )}
          {tableId && (
            <TableSyncStatus
              tableId={tableId}
              fields={fields}
              workspaceId={base?.workspace_id}
            />
          )}
          <Button onClick={handleCreateRow}>
            <Plus className="size-4" /> Row
          </Button>
        </div>
      </div>

      {drillFilter && (
        <div className="mb-3 flex items-center gap-2 self-start rounded-lg border border-accent-secondary/30 bg-accent-secondary-tint px-3 py-1.5 text-xs text-accent-secondary">
          <span>
            Filtered from dashboard:{" "}
            <span className="font-medium">{drillField}</span> ={" "}
            <span className="font-medium">{drillValue}</span>
          </span>
          <button
            type="button"
            onClick={clearDrillDown}
            className="rounded p-0.5 hover:bg-surface"
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}

      <ViewTabs
        tableId={table.id}
        views={table.views}
        fields={fields}
        activeViewId={activeView?.id ?? ""}
        onSelect={setActiveViewId}
      />

      {missingTermsOpen && tableId && (
        <MissingTermsPanel
          tableId={tableId}
          fields={fields}
          collapsed={missingTermsCollapsed}
          onToggleCollapse={() => setMissingTermsCollapsed((c) => !c)}
        />
      )}

      <div className="min-h-0 flex-1 overflow-auto">
        {activeView?.view_type === "kanban" ? (
          groupField ? (
            <KanbanBoard
              groupField={groupField}
              primaryField={primaryField}
              rows={displayRows}
              onMoveCard={(row, newValue) =>
                handleMoveCard(row, groupField, newValue)
              }
            />
          ) : (
            <p className="p-8 text-sm text-ink-tertiary">
              This board's group field was deleted — recreate the view.
            </p>
          )
        ) : activeView?.view_type === "form" ? (
          <FormViewPanel
            tableId={table.id}
            view={activeView}
            fields={fields}
            onSubmit={async (values) => {
              await createRecord.mutateAsync(values);
            }}
          />
        ) : (
          <DataGrid
            tableId={table.id}
            fields={gridFields}
            rows={displayRows}
            onCellCommit={handleCellCommit}
            onDeleteRow={handleDeleteRow}
            onExpandRow={(row) => setExpandedRowId(row.row_id)}
            onSubmitRow={
              submitConfig ? (row) => submitRow.mutate(row.row_id) : undefined
            }
            sort={sort}
            onSortChange={handleSortChange}
            filter={filter}
            onColumnFilterChange={handleColumnFilterChange}
            columnWidths={columnWidths}
            onColumnWidthChange={handleColumnWidthChange}
            onReorderColumns={handleReorderColumns}
            selectedRowIds={selectedRowIds}
            onToggleRowSelected={toggleRowSelected}
            onToggleSelectAll={toggleSelectAll}
            flashRowId={flashRowId}
            rowHeight={DENSITY_ROW_HEIGHT[density]}
            wrapText={wrapText}
            remoteFocusedCells={focusedCells}
            onActiveCellChange={sendCellFocus}
            onEditField={setEditFieldTarget}
            onDeleteField={setDeleteFieldTarget}
          />
        )}
      </div>

      {activeView?.view_type !== "form" && (
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <p className="text-xs text-ink-tertiary">
              {searchQuery ? (
                <>
                  {displayRows.length} of {rows.length} row
                  {rows.length === 1 ? "" : "s"} match
                </>
              ) : (
                <>
                  {rows.length} row{rows.length === 1 ? "" : "s"}
                  {isGridView ? ` on this page` : " loaded"}
                </>
              )}
            </p>
            {isGridView && (
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={handlePrevPage}
                  disabled={cursorHistory.length === 0}
                  className="flex items-center gap-0.5 rounded-md p-1 text-ink-tertiary transition-colors hover:bg-surface-raised hover:text-ink-secondary disabled:cursor-not-allowed disabled:opacity-30"
                  aria-label="Previous page"
                >
                  <ChevronLeft className="size-3.5" />
                </button>
                <span className="text-xs text-ink-tertiary">
                  Page {cursorHistory.length + 1}
                </span>
                <button
                  type="button"
                  onClick={handleNextPage}
                  disabled={!pagedQuery.data?.has_more}
                  className="flex items-center gap-0.5 rounded-md p-1 text-ink-tertiary transition-colors hover:bg-surface-raised hover:text-ink-secondary disabled:cursor-not-allowed disabled:opacity-30"
                  aria-label="Next page"
                >
                  <ChevronRight className="size-3.5" />
                </button>
                {pagedQuery.isFetching && (
                  <span className="text-xs text-ink-tertiary">Loading…</span>
                )}
              </div>
            )}
          </div>
          {selectedRowIds.size > 0 && (
            <div className="flex items-center gap-3 rounded-lg border border-border-default bg-surface px-3 py-1.5 shadow-sm">
              <span className="text-xs font-medium text-ink-secondary">
                {selectedRowIds.size} selected
              </span>
              <button
                type="button"
                onClick={() => setSelectedRowIds(new Set())}
                className="flex items-center gap-1 text-xs text-ink-tertiary hover:text-ink-secondary"
              >
                <X className="size-3" /> Clear
              </button>
              <button
                type="button"
                onClick={() => setBulkDeleteOpen(true)}
                className="flex items-center gap-1 text-xs font-medium text-status-danger hover:opacity-80"
              >
                <Trash2 className="size-3" /> Delete
              </button>
            </div>
          )}
        </div>
      )}

      {tableId && (
        <AddColumnDialog
          tableId={tableId}
          workspaceId={base?.workspace_id}
          fields={fields}
          open={addColumnOpen}
          onClose={() => setAddColumnOpen(false)}
        />
      )}
      {tableId && (
        <EditColumnDialog
          tableId={tableId}
          workspaceId={base?.workspace_id}
          field={editFieldTarget}
          onClose={() => setEditFieldTarget(null)}
        />
      )}
      {tableId && (
        <BulkUpdateDialog
          tableId={tableId}
          fields={fields}
          open={bulkUpdateOpen}
          onClose={() => setBulkUpdateOpen(false)}
        />
      )}
      {tableId && (
        <RowPoliciesDialog
          tableId={tableId}
          workspaceId={base?.workspace_id}
          fields={fields}
          open={rowPoliciesOpen}
          onClose={() => setRowPoliciesOpen(false)}
        />
      )}
      {tableId && activeView && (
        <GridFilterDialog
          tableId={tableId}
          view={activeView}
          fields={fields}
          open={filterOpen}
          onClose={() => setFilterOpen(false)}
        />
      )}
      {tableId && (
        <SubmitConfigDialog
          tableId={tableId}
          fields={fields}
          open={submitConfigOpen}
          onClose={() => setSubmitConfigOpen(false)}
        />
      )}
      {tableId && (
        <BatchSubmitConfigDialog
          tableId={tableId}
          fields={fields}
          open={batchSubmitConfigOpen}
          onClose={() => setBatchSubmitConfigOpen(false)}
        />
      )}
      {tableId && (
        <BatchSubmitDialog tableId={tableId} open={batchSubmitOpen} onClose={() => setBatchSubmitOpen(false)} />
      )}
      {tableId && (
        <MissingTermsConfigDialog
          tableId={tableId}
          fields={fields}
          open={missingTermsConfigOpen}
          onClose={() => setMissingTermsConfigOpen(false)}
        />
      )}
      {tableId && (
        <GroupCleanupDialog tableId={tableId} fields={fields} open={groupCleanupOpen} onClose={() => setGroupCleanupOpen(false)} />
      )}
      {tableId && (
        <JobResultsDialog
          tableId={tableId}
          jobId={jobResultsJobId}
          open={jobResultsJobId !== null}
          onClose={() => {
            setJobResultsJobId(null);
            if (missingTermsJobParam) {
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev);
                next.delete("missingTermsJob");
                return next;
              });
            }
          }}
        />
      )}
      {tableId && (
        <RowDetailDialog
          tableId={tableId}
          fields={fields}
          rows={displayRows}
          rowId={expandedRowId}
          onClose={() => setExpandedRowId(null)}
          onNavigate={setExpandedRowId}
          onCellCommit={handleCellCommit}
          onDeleteRow={handleDeleteRow}
        />
      )}
      <ConfirmDeleteDialog
        open={deleteRowTarget !== null}
        onClose={() => setDeleteRowTarget(null)}
        onConfirm={confirmDeleteRow}
        loading={deleteRecord.isPending}
        title="Delete row"
        description={
          deleteRowTarget
            ? `This permanently deletes ${
                primaryField && deleteRowTarget.values[primaryField.name]
                  ? `"${String(deleteRowTarget.values[primaryField.name])}"`
                  : `row #${deleteRowTarget.row_id}`
              }. This can't be undone.`
            : ""
        }
      />
      <ConfirmDeleteDialog
        open={bulkDeleteOpen}
        onClose={() => setBulkDeleteOpen(false)}
        onConfirm={confirmBulkDelete}
        loading={bulkDeleting}
        title="Delete rows"
        description={`This permanently deletes ${selectedRowIds.size} row${selectedRowIds.size === 1 ? "" : "s"}. This can't be undone.`}
      />
      <ConfirmDeleteDialog
        open={deleteFieldTarget !== null}
        onClose={() => setDeleteFieldTarget(null)}
        onConfirm={confirmDeleteField}
        loading={deleteField.isPending}
        title="Delete field"
        description={
          deleteFieldTarget
            ? `This permanently deletes the "${deleteFieldTarget.name}" field and all its data. This can't be undone.`
            : ""
        }
      />
    </div>
  );
}
