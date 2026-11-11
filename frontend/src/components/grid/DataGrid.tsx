import { useEffect, useMemo, useRef, useState } from "react";
import { createColumnHelper, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  AlignLeft,
  ArrowDown,
  ArrowUp,
  Calendar,
  CheckSquare,
  ChevronDown,
  FunctionSquare,
  Hash,
  Link2,
  Maximize2,
  Paperclip,
  Pencil,
  Search,
  Send,
  Sigma,
  Tag,
  Trash2,
  Type,
  X,
  type LucideIcon,
} from "lucide-react";
import type { Field, FieldTypeKey, FilterExpr, RecordRow, ViewSort } from "../../types";
import { coerceForField, filterExcludingField, getColumnFilterValues } from "../../lib/filterHelpers";
import { DropdownItem, DropdownMenu } from "../ui/DropdownMenu";
import { ColumnFilterDropdown } from "./ColumnFilterDropdown";
import { GridCell } from "./GridCell";

// Same ineligible set GridFilterDialog.tsx's own value-entry filter uses --
// no real column to compare/check against.
const NON_FILTERABLE_TYPES = new Set(["link_to_record", "lookup", "rollup", "formula", "attachment"]);

const DEFAULT_ROW_HEIGHT = 34;
const DEFAULT_COLUMN_WIDTH = 180;
const MIN_COLUMN_WIDTH = 80;
const ACTION_COLUMN_WIDTH = 64;
const SELECT_COLUMN_WIDTH = 32;

// A glanceable type indicator in the header -- the difference between a
// number column and a formula that happens to look numeric, or a real select
// vs. free text, isn't otherwise visible until you click into a cell.
// Computed server-side, never directly writable -- a multi-cell paste over
// one of these silently skips it instead of sending a write the API would
// reject anyway.
const VIRTUAL_FIELD_TYPES = new Set<string>(["lookup", "rollup", "formula"]);

const FIELD_TYPE_ICONS: Record<FieldTypeKey, LucideIcon> = {
  text: Type,
  long_text: AlignLeft,
  number: Hash,
  boolean: CheckSquare,
  date: Calendar,
  single_select: Tag,
  link_to_record: Link2,
  lookup: Search,
  rollup: Sigma,
  formula: FunctionSquare,
  attachment: Paperclip,
};

interface DataGridProps {
  tableId: string;
  fields: Field[];
  rows: RecordRow[];
  onCellCommit: (row: RecordRow, field: Field, value: unknown) => void;
  onDeleteRow: (row: RecordRow) => void;
  onExpandRow?: (row: RecordRow) => void;
  // "Submit row" action (POSTs the row to an external API, see
  // useRecordSubmit.ts) -- omitted entirely (no button, no action-gutter
  // widening) on any table with no submit target configured.
  onSubmitRow?: (row: RecordRow) => void;
  sort?: ViewSort[];
  onSortChange?: (field: string, additive: boolean) => void;
  // Excel-style AutoFilter checklist on each (filterable) column header --
  // omitted entirely wherever the caller has no view to persist a filter
  // into, e.g. a public shared view. `filter` is the view's whole FilterExpr
  // tree; this reads/writes just the one field a given header cell owns
  // (see lib/filterHelpers.ts).
  filter?: FilterExpr;
  onColumnFilterChange?: (fieldName: string, values: unknown[] | null) => void;
  columnWidths?: Record<string, number>;
  onColumnWidthChange?: (fieldId: string, width: number) => void;
  onReorderColumns?: (draggedFieldId: string, targetFieldId: string) => void;
  // Row selection for bulk actions (a floating toolbar the caller renders) --
  // omitted entirely (no checkbox column) when the caller doesn't pass these.
  selectedRowIds?: Set<number>;
  onToggleRowSelected?: (rowId: number) => void;
  onToggleSelectAll?: () => void;
  // Row-id to flash once (a brief accent-tint fade) right after it's created,
  // so a new row announces itself instead of silently appearing.
  flashRowId?: number | null;
  rowHeight?: number;
  // When true, cell text wraps instead of truncating and rows grow to fit
  // (see the virtualizer's measureElement wiring below) -- off by default,
  // matching every table's current fixed-height behavior exactly.
  wrapText?: boolean;
  // Presence: other users' currently-focused cells (userId -> {rowId,
  // fieldName}), and a callback fired whenever the local active cell moves,
  // so the caller can broadcast it over the table's WebSocket. Both omitted
  // entirely outside a live table view (e.g. nowhere yet, but keeps this
  // optional rather than coupling DataGrid to the live-updates hook).
  remoteFocusedCells?: Map<string, { userId: string; rowId: number; fieldName: string }>;
  onActiveCellChange?: (rowId: number, fieldName: string) => void;
  // Column header menu (rename/edit options, delete) -- omitted entirely
  // (no menu button rendered) wherever the caller has no write access to the
  // schema, e.g. a public shared view.
  onEditField?: (field: Field) => void;
  onDeleteField?: (field: Field) => void;
}

const columnHelper = createColumnHelper<RecordRow>();

function cellKey(rowIndex: number, fieldIndex: number): string {
  return `${rowIndex}:${fieldIndex}`;
}

export function DataGrid({
  tableId,
  fields,
  rows,
  onCellCommit,
  onDeleteRow,
  onExpandRow,
  onSubmitRow,
  sort,
  onSortChange,
  filter,
  onColumnFilterChange,
  columnWidths,
  onColumnWidthChange,
  onReorderColumns,
  selectedRowIds,
  onToggleRowSelected,
  onToggleSelectAll,
  flashRowId,
  rowHeight = DEFAULT_ROW_HEIGHT,
  wrapText = false,
  remoteFocusedCells,
  onActiveCellChange,
  onEditField,
  onDeleteField,
}: DataGridProps) {
  const selectAllRef = useRef<HTMLInputElement>(null);
  const parentRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);
  const cellRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const [localWidths, setLocalWidths] = useState<Record<string, number>>(columnWidths ?? {});
  const [dragOverFieldId, setDragOverFieldId] = useState<string | null>(null);
  const [activeCell, setActiveCell] = useState<{ rowIndex: number; fieldIndex: number } | null>(null);
  // The fixed corner of a multi-cell range -- null (or equal to activeCell)
  // means "just a single cell," matching how every spreadsheet distinguishes
  // a plain click from a shift-click/shift-arrow range.
  const [selectionAnchor, setSelectionAnchor] = useState<{ rowIndex: number; fieldIndex: number } | null>(null);
  // Only widens when a third button is actually rendered -- every table with
  // no submit target configured stays pixel-identical to before this existed.
  const actionColumnWidth = onSubmitRow ? ACTION_COLUMN_WIDTH + 32 : ACTION_COLUMN_WIDTH;

  useEffect(() => {
    setLocalWidths(columnWidths ?? {});
  }, [columnWidths]);

  function widthFor(fieldId: string): number {
    return localWidths[fieldId] ?? DEFAULT_COLUMN_WIDTH;
  }

  function startResize(e: React.MouseEvent, fieldId: string) {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startWidth = widthFor(fieldId);

    function handleMouseMove(moveEvent: MouseEvent) {
      const nextWidth = Math.max(MIN_COLUMN_WIDTH, startWidth + (moveEvent.clientX - startX));
      setLocalWidths((prev) => ({ ...prev, [fieldId]: nextWidth }));
    }
    function handleMouseUp(upEvent: MouseEvent) {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      const finalWidth = Math.max(MIN_COLUMN_WIDTH, startWidth + (upEvent.clientX - startX));
      onColumnWidthChange?.(fieldId, finalWidth);
    }
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  }

  const columns = useMemo(
    () =>
      fields.map((field) =>
        columnHelper.accessor((row) => row.values[field.name], {
          id: field.id,
          header: field.name,
        }),
      ),
    [fields],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const tableRows = table.getRowModel().rows;

  const selectedCount = selectedRowIds
    ? tableRows.reduce((n, r) => n + (selectedRowIds.has(r.original.row_id) ? 1 : 0), 0)
    : 0;
  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = selectedCount > 0 && selectedCount < tableRows.length;
    }
  }, [selectedCount, tableRows.length]);

  const virtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 10,
  });

  const virtualItems = virtualizer.getVirtualItems();

  // @tanstack/react-virtual caches each row's measured size and only
  // recomputes it lazily, keyed off things like item count -- changing what
  // estimateSize() *returns* (toggling row density) doesn't by itself
  // invalidate that cache, so already-rendered rows would silently keep
  // their old height without this explicit remeasure. wrapText is included
  // for the same reason: toggling it switches cells between truncating and
  // wrapping, which changes every rendered row's real height without
  // changing rowHeight itself.
  useEffect(() => {
    virtualizer.measure();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rowHeight, wrapText]);

  function moveActiveCell(rowIndex: number, fieldIndex: number, extendSelection = false, focusTarget = true) {
    const clampedRow = Math.max(0, Math.min(tableRows.length - 1, rowIndex));
    const clampedField = Math.max(0, Math.min(fields.length - 1, fieldIndex));
    setSelectionAnchor((prevAnchor) => (extendSelection ? (prevAnchor ?? activeCell) : { rowIndex: clampedRow, fieldIndex: clampedField }));
    setActiveCell({ rowIndex: clampedRow, fieldIndex: clampedField });
    virtualizer.scrollToIndex(clampedRow, { align: "auto" });
    if (clampedRow !== activeCell?.rowIndex || clampedField !== activeCell?.fieldIndex) {
      const targetRow = tableRows[clampedRow]?.original;
      const targetField = fields[clampedField];
      if (targetRow && targetField) onActiveCellChange?.(targetRow.row_id, targetField.name);
    }
    // A mouse click already gives the wrapper native focus-on-click (or, for a
    // plain click, is about to hand off to GridCell's own edit-mode input) --
    // forcing it again here would race that and can steal focus straight back
    // out of a just-opened editor. Only keyboard-driven moves need this.
    if (!focusTarget) return;
    requestAnimationFrame(() => {
      cellRefs.current.get(cellKey(clampedRow, clampedField))?.focus();
    });
  }

  const selectionBounds = (() => {
    if (!activeCell) return null;
    const anchor = selectionAnchor ?? activeCell;
    return {
      minRow: Math.min(anchor.rowIndex, activeCell.rowIndex),
      maxRow: Math.max(anchor.rowIndex, activeCell.rowIndex),
      minField: Math.min(anchor.fieldIndex, activeCell.fieldIndex),
      maxField: Math.max(anchor.fieldIndex, activeCell.fieldIndex),
    };
  })();
  const isMultiCellSelection = !!selectionBounds && (selectionBounds.minRow !== selectionBounds.maxRow || selectionBounds.minField !== selectionBounds.maxField);

  // Reverse-indexed by "rowId:fieldName" so rendering a cell is an O(1)
  // lookup instead of scanning every present user per cell per render.
  const remoteFocusByCell = useMemo(() => {
    const map = new Map<string, { userId: string }>();
    remoteFocusedCells?.forEach((focus) => map.set(`${focus.rowId}:${focus.fieldName}`, { userId: focus.userId }));
    return map;
  }, [remoteFocusedCells]);

  function handleCellKeyDown(e: React.KeyboardEvent<HTMLDivElement>, rowIndex: number, fieldIndex: number) {
    // Arrow keys and Tab only navigate when the wrapper itself is focused --
    // while GridCell is editing, an inner <input>/<select> holds focus and
    // this handler still fires via bubbling, so those keys must move the text
    // cursor/selection there instead of the active cell. Enter is exempt: a
    // single-line <input> has no use for Enter itself, and GridCell's own
    // handler already commits on Enter (via the input's onKeyDown, which
    // fires first) -- letting it also fall through here gives the standard
    // spreadsheet "Enter commits and moves down" behavior even mid-edit.
    const isEditingChild = e.target !== e.currentTarget;

    // Ctrl/Cmd+C and +V: a plain (non-editing) cell wrapper is just a <div>
    // with nothing "selected" from the browser's point of view, so the
    // native copy/paste DOM events never fire on it -- the Clipboard API is
    // used directly instead. While editing, an inner <input> has its own
    // real text selection, so those native events already work there and
    // this is skipped to avoid double-handling.
    // A multi-cell range (shift-click or shift-arrow) copies/pastes as a
    // tab/newline-delimited block, same as every spreadsheet's clipboard
    // format -- a single active cell is just the degenerate 1x1 case.
    if (!isEditingChild && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c") {
      e.preventDefault();
      const bounds = selectionBounds ?? { minRow: rowIndex, maxRow: rowIndex, minField: fieldIndex, maxField: fieldIndex };
      const lines: string[] = [];
      for (let r = bounds.minRow; r <= bounds.maxRow; r++) {
        const row = tableRows[r]?.original;
        const cells: string[] = [];
        for (let f = bounds.minField; f <= bounds.maxField; f++) {
          const field = fields[f];
          const value = row && field ? row.values[field.name] : undefined;
          cells.push(value == null ? "" : String(value));
        }
        lines.push(cells.join("\t"));
      }
      void navigator.clipboard.writeText(lines.join("\n"));
      return;
    }
    if (!isEditingChild && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "v") {
      e.preventDefault();
      void navigator.clipboard.readText().then((text) => {
        const parsedRows = text.replace(/\r/g, "").split("\n").filter((line, i, arr) => !(i === arr.length - 1 && line === ""));
        const parsed = parsedRows.map((line) => line.split("\t"));
        const bounds = selectionBounds ?? { minRow: rowIndex, maxRow: rowIndex, minField: fieldIndex, maxField: fieldIndex };
        const isSingleValue = parsed.length === 1 && parsed[0].length === 1;
        // Pasting one value onto a multi-cell selection fills the whole
        // range with it (e.g. select a column of cells, paste one number) --
        // otherwise the clipboard's own shape is written starting at the
        // selection's top-left corner, clamped to the grid's bounds.
        const rowSpan = isSingleValue && isMultiCellSelection ? bounds.maxRow - bounds.minRow + 1 : parsed.length;
        for (let r = 0; r < rowSpan; r++) {
          const targetRow = bounds.minRow + r;
          if (targetRow > tableRows.length - 1) break;
          const row = tableRows[targetRow]?.original;
          if (!row) continue;
          const parsedRow = isSingleValue ? parsed[0] : parsed[r];
          if (!parsedRow) continue;
          const colSpan = isSingleValue && isMultiCellSelection ? bounds.maxField - bounds.minField + 1 : parsedRow.length;
          for (let c = 0; c < colSpan; c++) {
            const targetField = bounds.minField + c;
            if (targetField > fields.length - 1) break;
            const field = fields[targetField];
            if (!field || VIRTUAL_FIELD_TYPES.has(field.field_type)) continue;
            const rawValue = isSingleValue ? parsedRow[0] : parsedRow[c];
            if (rawValue === undefined) continue;
            onCellCommit(row, field, coerceForField(field, rawValue));
          }
        }
      });
      return;
    }

    if (isEditingChild && e.key !== "Enter") return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        moveActiveCell(rowIndex + 1, fieldIndex, e.shiftKey);
        return;
      case "ArrowUp":
        e.preventDefault();
        moveActiveCell(rowIndex - 1, fieldIndex, e.shiftKey);
        return;
      case "ArrowRight":
        e.preventDefault();
        moveActiveCell(rowIndex, fieldIndex + 1, e.shiftKey);
        return;
      case "ArrowLeft":
        e.preventDefault();
        moveActiveCell(rowIndex, fieldIndex - 1, e.shiftKey);
        return;
      case "Tab":
        e.preventDefault();
        moveActiveCell(rowIndex, fieldIndex + (e.shiftKey ? -1 : 1));
        return;
      case "Enter":
        e.preventDefault();
        moveActiveCell(rowIndex + (e.shiftKey ? -1 : 1), fieldIndex);
        return;
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-border-default bg-surface">
      {/* z-10 is load-bearing, not decorative: the horizontal-scroll-sync
          transform above gives this row its own stacking context the moment
          it's non-identity, which otherwise traps an open column-header
          dropdown's z-50 behind it -- the body (a later DOM sibling, with no
          stacking order of its own) would then paint over the whole header,
          dropdown included. */}
      <div
        ref={headerRef}
        className="relative z-10 flex border-b-2 border-border-strong bg-surface text-[11px] font-medium uppercase tracking-wide text-ink-tertiary"
      >
        {onToggleSelectAll && (
          <div style={{ width: SELECT_COLUMN_WIDTH }} className="flex shrink-0 items-center justify-center py-2.5">
            <input
              ref={selectAllRef}
              type="checkbox"
              className="accent-accent-secondary"
              checked={tableRows.length > 0 && selectedCount === tableRows.length}
              onChange={onToggleSelectAll}
              title="Select all rows on this page"
              aria-label="Select all rows on this page"
            />
          </div>
        )}
        <div style={{ width: actionColumnWidth }} className="shrink-0 px-2 py-2.5" />
        {table.getHeaderGroups()[0].headers.map((header) => {
          const fieldName = String(header.column.columnDef.header);
          const fieldId = header.column.id;
          const field = fields.find((f) => f.id === fieldId);
          const TypeIcon = field ? FIELD_TYPE_ICONS[field.field_type as FieldTypeKey] : undefined;
          const sortIndex = sort?.findIndex((s) => s.field === fieldName) ?? -1;
          const sortSpec = sortIndex >= 0 ? sort?.[sortIndex] : undefined;
          const isDragOver = dragOverFieldId === fieldId;
          return (
            <div
              key={header.id}
              draggable={!!onReorderColumns}
              onDragStart={(e) => e.dataTransfer.setData("text/plain", fieldId)}
              onDragOver={(e) => {
                if (!onReorderColumns) return;
                e.preventDefault();
                setDragOverFieldId(fieldId);
              }}
              onDragLeave={() => setDragOverFieldId((prev) => (prev === fieldId ? null : prev))}
              onDrop={(e) => {
                e.preventDefault();
                setDragOverFieldId(null);
                const draggedId = e.dataTransfer.getData("text/plain");
                if (draggedId && draggedId !== fieldId) onReorderColumns?.(draggedId, fieldId);
              }}
              style={{ width: widthFor(fieldId) }}
              data-header-field={fieldName}
              className={`group/header relative flex shrink-0 items-center border-l border-border-default first:border-l-0 ${isDragOver ? "bg-accent-secondary-tint" : ""}`}
            >
              <button
                type="button"
                disabled={!onSortChange}
                onClick={(e) => onSortChange?.(fieldName, e.shiftKey)}
                className="flex min-w-0 flex-1 items-center gap-1 truncate px-2.5 py-2 text-left enabled:hover:text-ink-secondary"
                title={onSortChange ? "Click to sort, shift-click to add a secondary sort, drag to reorder" : undefined}
              >
                {TypeIcon && <TypeIcon className="size-3 shrink-0 text-ink-tertiary" strokeWidth={2} />}
                <span className="truncate">{fieldName}</span>
                {sortSpec &&
                  (sortSpec.direction === "asc" ? <ArrowUp className="size-3 shrink-0" /> : <ArrowDown className="size-3 shrink-0" />)}
                {sortSpec && (sort?.length ?? 0) > 1 && (
                  <span className="flex size-3.5 shrink-0 items-center justify-center rounded-full bg-accent-secondary-tint text-[9px] font-semibold text-accent-secondary">
                    {sortIndex + 1}
                  </span>
                )}
              </button>
              {onColumnFilterChange && field && !NON_FILTERABLE_TYPES.has(field.field_type) && (
                <ColumnFilterDropdown
                  field={field}
                  currentValues={getColumnFilterValues(filter, fieldName)}
                  otherFilters={filterExcludingField(filter, fieldName)}
                  onApply={(values) => onColumnFilterChange(fieldName, values)}
                />
              )}
              {(onEditField || onDeleteField) && field && (
                <DropdownMenu
                  align="left"
                  triggerClassName="mr-1 shrink-0"
                  trigger={<ChevronDown className="size-3 text-ink-tertiary" />}
                >
                  {onEditField && <DropdownItem onClick={() => onEditField(field)}>
                    <Pencil className="size-3.5" /> Edit field
                  </DropdownItem>}
                  {onDeleteField && !field.is_primary && (
                    <DropdownItem onClick={() => onDeleteField(field)} className="text-status-danger hover:text-status-danger">
                      <Trash2 className="size-3.5" /> Delete field
                    </DropdownItem>
                  )}
                </DropdownMenu>
              )}
              {onColumnWidthChange && (
                <div
                  onMouseDown={(e) => startResize(e, fieldId)}
                  className="absolute right-0 top-0 h-full w-1.5 shrink-0 cursor-col-resize opacity-0 hover:bg-accent-secondary group-hover/header:opacity-100"
                />
              )}
            </div>
          );
        })}
      </div>

      <div
        ref={parentRef}
        className="flex-1 overflow-auto"
        onScroll={(e) => {
          // The header lives in its own sibling div, outside the scrollable
          // body, so it never moves on its own -- mirror the body's
          // horizontal scroll onto it directly (skipping React state/render)
          // so header labels stay aligned with their columns while scrolling.
          if (headerRef.current) headerRef.current.style.transform = `translateX(${-e.currentTarget.scrollLeft}px)`;
        }}
      >
        <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
          {virtualItems.map((virtualRow) => {
            const row = tableRows[virtualRow.index].original;
            return (
              <div
                key={row.row_id}
                ref={virtualizer.measureElement}
                data-index={virtualRow.index}
                className={`group absolute left-0 top-0 flex w-full border-b border-border-default transition-colors hover:bg-surface-raised ${
                  selectedRowIds?.has(row.row_id)
                    ? "bg-accent-secondary-tint"
                    : virtualRow.index % 2 === 1
                      ? "bg-canvas/40"
                      : ""
                } ${row.row_id === flashRowId ? "animate-row-flash" : ""}`}
                style={{ minHeight: virtualRow.size, transform: `translateY(${virtualRow.start}px)` }}
              >
                {onToggleRowSelected && (
                  <div style={{ width: SELECT_COLUMN_WIDTH }} className="flex shrink-0 items-center justify-center">
                    <input
                      type="checkbox"
                      className="accent-accent-secondary"
                      checked={selectedRowIds?.has(row.row_id) ?? false}
                      onChange={() => onToggleRowSelected(row.row_id)}
                      aria-label={`Select row ${row.row_id}`}
                    />
                  </div>
                )}
                <div style={{ width: actionColumnWidth }} className="flex shrink-0 items-center justify-center gap-0.5">
                  {onExpandRow && (
                    <button
                      className="rounded p-0.5 text-ink-tertiary opacity-0 transition-opacity hover:bg-accent-secondary-tint hover:text-accent-secondary group-hover:opacity-100"
                      title="Expand row"
                      onClick={() => onExpandRow(row)}
                    >
                      <Maximize2 className="size-3.5" />
                    </button>
                  )}
                  {onSubmitRow && (
                    <button
                      className="rounded p-0.5 text-ink-tertiary opacity-0 transition-opacity hover:bg-accent-secondary-tint hover:text-accent-secondary group-hover:opacity-100"
                      title="Submit row"
                      onClick={() => onSubmitRow(row)}
                    >
                      <Send className="size-3.5" />
                    </button>
                  )}
                  <button
                    className="rounded p-0.5 text-ink-tertiary opacity-0 transition-opacity hover:bg-status-danger-tint hover:text-status-danger group-hover:opacity-100"
                    title="Delete row"
                    onClick={() => onDeleteRow(row)}
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
                {fields.map((field, fieldIndex) => {
                  const isActive = activeCell?.rowIndex === virtualRow.index && activeCell?.fieldIndex === fieldIndex;
                  const inRange =
                    isMultiCellSelection &&
                    !!selectionBounds &&
                    virtualRow.index >= selectionBounds.minRow &&
                    virtualRow.index <= selectionBounds.maxRow &&
                    fieldIndex >= selectionBounds.minField &&
                    fieldIndex <= selectionBounds.maxField;
                  const remoteFocus = remoteFocusByCell.get(`${row.row_id}:${field.name}`);
                  return (
                    <div
                      key={field.id}
                      ref={(el) => {
                        if (el) cellRefs.current.set(cellKey(virtualRow.index, fieldIndex), el);
                        else cellRefs.current.delete(cellKey(virtualRow.index, fieldIndex));
                      }}
                      tabIndex={0}
                      data-cell={cellKey(virtualRow.index, fieldIndex)}
                      data-field-name={field.name}
                      style={{ width: widthFor(field.id) }}
                      title={remoteFocus ? "Someone else is editing this cell" : undefined}
                      className={`relative shrink-0 border-l border-border-default outline-none first:border-l-0 ${
                        isActive ? "ring-2 ring-inset ring-accent-secondary" : inRange ? "bg-selection" : ""
                      } ${remoteFocus ? "ring-2 ring-inset ring-accent" : ""}`}
                      onFocus={() => setActiveCell({ rowIndex: virtualRow.index, fieldIndex })}
                      onMouseDown={(e) => {
                        // A click on the cell's displayed (non-editing) content should
                        // start/extend a range -- but a click inside an actively-editing
                        // <input>/<select> must just place the text cursor/pick an option,
                        // not steal focus back to the wrapper mid-edit.
                        const targetTag = (e.target as HTMLElement).tagName;
                        if (targetTag === "INPUT" || targetTag === "SELECT" || targetTag === "TEXTAREA") return;
                        if (e.shiftKey) e.preventDefault();
                        moveActiveCell(virtualRow.index, fieldIndex, e.shiftKey, false);
                      }}
                      onKeyDown={(e) => handleCellKeyDown(e, virtualRow.index, fieldIndex)}
                    >
                      <GridCell
                        tableId={tableId}
                        rowId={row.row_id}
                        field={field}
                        value={row.values[field.name]}
                        wrapText={wrapText}
                        onCommit={(value) => {
                          onCellCommit(row, field, value);
                          requestAnimationFrame(() => {
                            cellRefs.current.get(cellKey(virtualRow.index, fieldIndex))?.focus();
                          });
                        }}
                      />
                      {remoteFocus && <span className="absolute right-0.5 top-0.5 size-1.5 rounded-full bg-accent" />}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
