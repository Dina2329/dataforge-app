import { useState, type DragEvent } from "react";
import type { Field, FieldOption, RecordRow } from "../../types";

const NO_STATUS_VALUE = "__no_status__";

interface KanbanBoardProps {
  groupField: Field;
  primaryField: Field | undefined;
  rows: RecordRow[];
  onMoveCard: (row: RecordRow, newValue: string | null) => void;
}

export function KanbanBoard({ groupField, primaryField, rows, onMoveCard }: KanbanBoardProps) {
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);
  const choices = (groupField.options.choices ?? []) as FieldOption[];
  const columns: { value: string; label: string }[] = [...choices, { value: NO_STATUS_VALUE, label: "No status" }];

  function rowsForColumn(columnValue: string): RecordRow[] {
    return rows.filter((row) => {
      const value = row.values[groupField.name];
      if (columnValue === NO_STATUS_VALUE) return value == null || !choices.some((c) => c.value === value);
      return value === columnValue;
    });
  }

  function handleDrop(e: DragEvent<HTMLDivElement>, columnValue: string) {
    e.preventDefault();
    setDragOverColumn(null);
    const rowId = Number(e.dataTransfer.getData("text/plain"));
    const row = rows.find((r) => r.row_id === rowId);
    if (!row) return;
    const currentValue = row.values[groupField.name];
    const nextValue = columnValue === NO_STATUS_VALUE ? null : columnValue;
    if (currentValue === nextValue) return;
    onMoveCard(row, nextValue);
  }

  return (
    <div className="flex h-full gap-3 overflow-x-auto pb-2">
      {columns.map((column) => {
        const columnRows = rowsForColumn(column.value);
        return (
          <div
            key={column.value}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOverColumn(column.value);
            }}
            onDragLeave={() => setDragOverColumn((prev) => (prev === column.value ? null : prev))}
            onDrop={(e) => handleDrop(e, column.value)}
            className={`flex w-64 shrink-0 flex-col rounded-xl bg-surface-raised p-2 transition-colors ${
              dragOverColumn === column.value ? "bg-accent-secondary-tint ring-2 ring-accent-secondary/30" : ""
            }`}
          >
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-ink-tertiary">{column.label}</span>
              <span className="rounded-full bg-surface px-1.5 py-0.5 text-xs text-ink-tertiary border border-border-default">
                {columnRows.length}
              </span>
            </div>
            <div className="flex-1 space-y-2 overflow-y-auto">
              {columnRows.map((row) => (
                <div
                  key={row.row_id}
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData("text/plain", String(row.row_id))}
                  className="cursor-grab rounded-lg bg-surface p-2.5 text-sm text-ink-primary shadow-sm border border-border-default active:cursor-grabbing"
                >
                  {primaryField ? String(row.values[primaryField.name] ?? `Row ${row.row_id}`) : `Row ${row.row_id}`}
                </div>
              ))}
              {columnRows.length === 0 && <div className="rounded-lg border border-dashed border-border-default p-3 text-center text-xs text-ink-tertiary">Drop here</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
