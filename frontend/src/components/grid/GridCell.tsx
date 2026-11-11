import { useState, type KeyboardEvent } from "react";
import { Link2 } from "lucide-react";
import type { Field, LinkValue } from "../../types";
import { AttachmentCell } from "./AttachmentCell";
import { LinkPickerDialog } from "./LinkPickerDialog";

interface GridCellProps {
  field: Field;
  value: unknown;
  onCommit: (value: unknown) => void;
  tableId: string;
  rowId: number;
  // Off by default (every existing table's exact current truncating
  // behavior). Only text/long_text and the virtual read-only types wrap --
  // number/date are short, fixed-format values that don't have the
  // "overflowing content" problem wrap exists to solve, and single_select/
  // link_to_record render as compact pills, not something wrap fits well.
  wrapText?: boolean;
}

const VIRTUAL_READONLY_TYPES = new Set(["lookup", "rollup", "formula"]);
const NUMERIC_LIKE_TYPES = new Set(["number"]);
const WRAPPABLE_TYPES = new Set(["text", "long_text"]);

export function GridCell({ field, value, onCommit, tableId, rowId, wrapText = false }: GridCellProps) {
  const [editing, setEditing] = useState(false);
  const [linkPickerOpen, setLinkPickerOpen] = useState(false);
  const [draft, setDraft] = useState<string>(value == null ? "" : String(value));

  function startEdit() {
    setDraft(value == null ? "" : String(value));
    setEditing(true);
  }

  function commit() {
    setEditing(false);
    if (field.field_type === "boolean") return; // boolean commits immediately on toggle
    if (field.field_type === "number") {
      onCommit(draft === "" ? null : Number(draft));
    } else {
      onCommit(draft === "" ? null : draft);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement | HTMLSelectElement>) {
    if (e.key === "Enter") commit();
    if (e.key === "Escape") setEditing(false);
  }

  if (field.field_type === "attachment") {
    return <AttachmentCell tableId={tableId} rowId={rowId} fieldId={field.id} value={value} />;
  }

  if (field.field_type === "boolean") {
    return (
      <div className="flex h-full items-center px-2">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onCommit(e.target.checked)}
          className="h-3.5 w-3.5 accent-accent"
        />
      </div>
    );
  }

  if (field.field_type === "link_to_record") {
    const links = (value as LinkValue[] | null) ?? [];
    return (
      <>
        <div className="flex h-full cursor-pointer items-center gap-1 overflow-hidden px-2" onClick={() => setLinkPickerOpen(true)}>
          {links.length === 0 ? (
            <span className="inline-flex items-center gap-1 text-ink-tertiary">
              <Link2 className="size-3" /> —
            </span>
          ) : (
            links.map((link) => (
              <span
                key={link.row_id}
                className="shrink-0 truncate rounded-full bg-accent-secondary-tint px-1.5 py-0.5 text-xs font-medium text-accent-secondary"
              >
                {link.display ?? `#${link.row_id}`}
              </span>
            ))
          )}
        </div>
        {field.options.target_table_id && (
          <LinkPickerDialog
            targetTableId={field.options.target_table_id}
            selectedRowIds={links.map((l) => l.row_id)}
            open={linkPickerOpen}
            onClose={() => setLinkPickerOpen(false)}
            onSave={(rowIds) => {
              onCommit(rowIds);
              setLinkPickerOpen(false);
            }}
          />
        )}
      </>
    );
  }

  if (VIRTUAL_READONLY_TYPES.has(field.field_type)) {
    const display = Array.isArray(value) ? value.map((v) => (v == null ? "" : String(v))).join(", ") : value;
    return (
      <div
        className={`flex cursor-default px-2 text-sm italic text-ink-tertiary ${
          wrapText ? "items-start whitespace-pre-wrap break-words py-1.5" : "h-full items-center truncate"
        }`}
        title={wrapText ? undefined : display == null ? "" : String(display)}
      >
        {display == null || display === "" ? <span className="text-ink-tertiary/70">—</span> : String(display)}
      </div>
    );
  }

  if (!editing) {
    // A chosen single-select value gets a neutral chip -- distinct from the
    // link_to_record chip's accent-secondary tint, so at a glance a chip's
    // color already tells you "this points to another record" vs "this is
    // this row's own status/category" without reading the field type.
    if (field.field_type === "single_select" && value) {
      const choice = ((field.options.choices ?? []) as { value: string; label: string }[]).find((c) => c.value === value);
      return (
        <div className="flex h-full cursor-text items-center px-2" onClick={startEdit}>
          <span className="truncate rounded-full bg-surface-raised px-1.5 py-0.5 text-xs font-medium text-ink-primary ring-1 ring-inset ring-border-strong">
            {choice?.label ?? String(value)}
          </span>
        </div>
      );
    }
    const shouldWrap = wrapText && WRAPPABLE_TYPES.has(field.field_type);
    return (
      <div
        className={`flex cursor-text px-2 text-sm text-ink-primary ${NUMERIC_LIKE_TYPES.has(field.field_type) ? "font-mono tabular-nums" : ""} ${
          shouldWrap ? "items-start whitespace-pre-wrap break-words py-1.5" : "h-full items-center truncate"
        }`}
        onClick={startEdit}
        title={shouldWrap ? undefined : value == null ? "" : String(value)}
      >
        {value == null || value === "" ? <span className="text-ink-tertiary">—</span> : String(value)}
      </div>
    );
  }

  if (field.field_type === "single_select") {
    const choices = (field.options.choices ?? []) as { value: string; label: string }[];
    return (
      <select
        autoFocus
        className="h-full w-full border-2 border-accent-secondary bg-surface px-2 text-sm text-ink-primary outline-none"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={handleKeyDown}
      >
        <option value="">—</option>
        {choices.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </select>
    );
  }

  return (
    <input
      autoFocus
      type={field.field_type === "number" ? "number" : field.field_type === "date" ? "date" : "text"}
      className={`h-full w-full border-2 border-accent-secondary bg-surface px-2 text-sm text-ink-primary outline-none ${field.field_type === "number" ? "font-mono" : ""}`}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={handleKeyDown}
    />
  );
}
