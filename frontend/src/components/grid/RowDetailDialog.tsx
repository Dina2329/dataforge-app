import { ChevronDown, ChevronUp, Trash2 } from "lucide-react";
import type { Field, RecordRow } from "../../types";
import { Dialog } from "../ui/Dialog";
import { GridCell } from "./GridCell";

interface RowDetailDialogProps {
  tableId: string;
  fields: Field[];
  rows: RecordRow[];
  rowId: number | null;
  onClose: () => void;
  onNavigate: (rowId: number) => void;
  onCellCommit: (row: RecordRow, field: Field, value: unknown) => void;
  onDeleteRow: (row: RecordRow) => void;
}

export function RowDetailDialog({ tableId, fields, rows, rowId, onClose, onNavigate, onCellCommit, onDeleteRow }: RowDetailDialogProps) {
  const index = rows.findIndex((r) => r.row_id === rowId);
  const row = index >= 0 ? rows[index] : undefined;

  if (!row) return null;

  const primaryField = fields.find((f) => f.is_primary);
  const title = primaryField ? String(row.values[primaryField.name] ?? `Row #${row.row_id}`) : `Row #${row.row_id}`;

  return (
    <Dialog open onClose={onClose} title={title} size="lg">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={index <= 0}
            onClick={() => onNavigate(rows[index - 1].row_id)}
            className="rounded p-1 text-ink-tertiary hover:bg-surface-raised hover:text-ink-secondary disabled:cursor-not-allowed disabled:opacity-30"
            title="Previous row"
          >
            <ChevronUp className="size-4" />
          </button>
          <button
            type="button"
            disabled={index === -1 || index >= rows.length - 1}
            onClick={() => onNavigate(rows[index + 1].row_id)}
            className="rounded p-1 text-ink-tertiary hover:bg-surface-raised hover:text-ink-secondary disabled:cursor-not-allowed disabled:opacity-30"
            title="Next row"
          >
            <ChevronDown className="size-4" />
          </button>
          <span className="ml-1 text-xs text-ink-tertiary">
            {index + 1} of {rows.length}
          </span>
        </div>
        <button
          type="button"
          onClick={() => {
            onDeleteRow(row);
            onClose();
          }}
          className="flex items-center gap-1 rounded p-1 text-xs text-ink-tertiary hover:bg-status-danger-tint hover:text-status-danger"
          title="Delete row"
        >
          <Trash2 className="size-3.5" /> Delete
        </button>
      </div>

      <div className="max-h-[60vh] space-y-1 overflow-y-auto pr-1">
        {fields.map((field) => (
          <div key={field.id} className="grid grid-cols-[9rem_1fr] items-stretch gap-2">
            <label className="flex items-center truncate text-xs font-medium text-ink-secondary">{field.name}</label>
            {/* min-w-0 is load-bearing: a grid column defaults to shrinking no
               further than its content's natural (unwrapped) width, which is
               exactly what was forcing this whole dialog to scroll
               horizontally instead of actually truncating/wrapping a long
               value -- min-h-9 (not a fixed h-9) for the same reason on the
               vertical axis, so wrapText below can grow the cell instead of
               clipping it. Always wrapped, unlike the main grid's own
               toggle -- this view only ever shows one row at a time, so
               there's no "scan many rows quickly" reason to truncate here. */}
            <div className="min-h-9 min-w-0 rounded-md border border-border-default">
              <GridCell
                tableId={tableId}
                rowId={row.row_id}
                field={field}
                value={row.values[field.name]}
                wrapText
                onCommit={(value) => onCellCommit(row, field, value)}
              />
            </div>
          </div>
        ))}
      </div>
    </Dialog>
  );
}
