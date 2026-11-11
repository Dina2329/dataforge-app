import { Plus, X } from "lucide-react";
import { FILTER_OPERATORS, type Field, type FilterOperator } from "../../types";
import { emptyFilterRow, NO_VALUE_OPERATORS, OPERATOR_LABELS, type FilterRow } from "../../lib/filterHelpers";
import { Select } from "../ui/Select";
import { FieldValueInput } from "./FieldValueInput";
import { DistinctValuePicker } from "../grid/DistinctValuePicker";

const DISTINCT_VALUE_PICKER_TYPES = new Set(["text", "long_text"]);

interface FilterRowsEditorProps {
  fields: Field[];
  rows: FilterRow[];
  onChange: (rows: FilterRow[]) => void;
  emptyMessage?: string;
}

/** A flat list of field/operator/value rows, ANDed together -- the editable
 * form of a FilterExpr (see lib/filterHelpers.ts's rowsToFilterExpr/
 * filterExprToRows). Purely controlled: the caller owns the FilterRow[]
 * state and passes it back in via `rows`, this just renders it and reports
 * edits through `onChange`. Shared by the classic Filter dialog
 * (GridFilterDialog) and Batch Submit's "which rows are ready to send"
 * condition -- same row-building UI, bound to a different table's fields
 * and a different ultimate destination for the resulting FilterExpr. */
export function FilterRowsEditor({ fields, rows, onChange, emptyMessage = "No conditions yet." }: FilterRowsEditorProps) {
  function updateRow(key: number, patch: Partial<FilterRow>) {
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  function removeRow(key: number) {
    onChange(rows.filter((r) => r.key !== key));
  }

  function addRow() {
    onChange([...rows, emptyFilterRow(fields[0]?.name ?? "")]);
  }

  return (
    <div>
      {rows.length === 0 ? (
        <p className="mb-3 text-sm text-ink-tertiary">{emptyMessage}</p>
      ) : (
        <div className="mb-3 space-y-2">
          {rows.map((row) => {
            const field = fields.find((f) => f.name === row.field);
            return (
              <div key={row.key} className="flex items-center gap-1.5">
                <div className="w-32 shrink-0">
                  <Select value={row.field} onChange={(e) => updateRow(row.key, { field: e.target.value, valueRaw: "" })}>
                    {fields.map((f) => (
                      <option key={f.id} value={f.name}>
                        {f.name}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="w-36 shrink-0">
                  <Select value={row.operator} onChange={(e) => updateRow(row.key, { operator: e.target.value as FilterOperator })}>
                    {FILTER_OPERATORS.map((op) => (
                      <option key={op} value={op}>
                        {OPERATOR_LABELS[op]}
                      </option>
                    ))}
                  </Select>
                </div>
                {!NO_VALUE_OPERATORS.has(row.operator) &&
                  (field && DISTINCT_VALUE_PICKER_TYPES.has(field.field_type) ? (
                    <DistinctValuePicker
                      fieldId={field.id}
                      value={row.valueRaw}
                      onChange={(v) => updateRow(row.key, { valueRaw: v })}
                      className="flex-1"
                    />
                  ) : (
                    <FieldValueInput field={field} value={row.valueRaw} onChange={(v) => updateRow(row.key, { valueRaw: v })} className="flex-1" />
                  ))}
                <button
                  type="button"
                  aria-label="Remove condition"
                  className="shrink-0 rounded p-1 text-ink-tertiary hover:bg-status-danger-tint hover:text-status-danger"
                  onClick={() => removeRow(row.key)}
                >
                  <X className="size-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <button
        type="button"
        onClick={addRow}
        className="mb-1 flex items-center gap-1 text-xs font-medium text-accent-secondary hover:opacity-80"
      >
        <Plus className="size-3.5" /> Add condition
      </button>

      {rows.length > 1 && <p className="text-xs text-ink-tertiary">All conditions must match (AND).</p>}
    </div>
  );
}
