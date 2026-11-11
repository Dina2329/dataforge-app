import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { useCreateAutomationAction } from "../../hooks/useAutomations";
import { useTable, useTables } from "../../hooks/useBases";
import { apiErrorMessage } from "../../lib/apiClient";
import { ACTION_TYPES, type ActionType, type Field, type TriggerType } from "../../types";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";
import { FieldValueInput } from "../shared/FieldValueInput";

export const ACTION_LABELS: Record<ActionType, string> = {
  send_webhook: "Send a webhook",
  create_record: "Create a record",
  update_record: "Update the triggering record",
};

// Virtual field types have no real column to write to (link_to_record's
// value is a list of row ids managed through its own link table; lookup/
// rollup/formula are computed, never stored) and attachments go through
// their own upload endpoint -- none of these can be a plain "set to a
// value" target, so the field picker below never offers them.
const NON_WRITABLE_TYPES = new Set(["link_to_record", "lookup", "rollup", "formula", "attachment"]);

interface ValueRow {
  key: number;
  fieldName: string;
  mode: "fixed" | "copy";
  fixedValue: string;
  copyFromField: string;
}

let nextRowKey = 1;
function emptyRow(): ValueRow {
  return { key: nextRowKey++, fieldName: "", mode: "fixed", fixedValue: "", copyFromField: "" };
}

// One made-up value per plain field type, used only to build a realistic-
// looking example payload below -- never sent anywhere.
const EXAMPLE_VALUE_BY_TYPE: Partial<Record<string, (field: Field) => unknown>> = {
  text: () => "Draft press release",
  long_text: () => "Needs one more review pass before it goes out.",
  number: () => 42,
  boolean: () => true,
  date: () => "2026-09-20",
  single_select: (field) => (field.options.choices as { value: string }[] | undefined)?.[0]?.value ?? "Todo",
};

function exampleRowValues(fields: Field[]): Record<string, unknown> {
  const plainFields = fields.filter((f) => !NON_WRITABLE_TYPES.has(f.field_type)).slice(0, 4);
  const values: Record<string, unknown> = {};
  for (const field of plainFields) {
    values[field.name] = (EXAMPLE_VALUE_BY_TYPE[field.field_type] ?? (() => "example value"))(field);
  }
  // A brand-new table with only link/lookup/computed fields would otherwise
  // show an empty example -- fall back to something recognizable instead.
  return Object.keys(values).length > 0 ? values : { Title: "Draft press release" };
}

interface AddActionDialogProps {
  automationId: string;
  baseId: string | undefined;
  sourceFields: Field[];
  triggerType: TriggerType | undefined;
  open: boolean;
  onClose: () => void;
}

export function AddActionDialog({ automationId, baseId, sourceFields, triggerType, open, onClose }: AddActionDialogProps) {
  const createAction = useCreateAutomationAction(automationId);
  const { data: tables } = useTables(baseId);
  const [actionType, setActionType] = useState<ActionType>("send_webhook");
  const [url, setUrl] = useState("");
  const [targetTableId, setTargetTableId] = useState("");
  const { data: targetTable } = useTable(actionType === "create_record" ? targetTableId : undefined);
  const [rows, setRows] = useState<ValueRow[]>([emptyRow()]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setActionType("send_webhook");
    setUrl("");
    setTargetTableId("");
    setRows([emptyRow()]);
    setError(null);
  }, [open]);

  // update_record writes to the automation's own table; create_record writes
  // to whichever table was picked as the target -- the field picker always
  // reflects the table actually being written to, and never offers a
  // virtual/computed field as a write target.
  const allWritableFields = actionType === "create_record" ? (targetTable?.fields ?? []) : sourceFields;
  const writableFields = allWritableFields.filter((f) => !NON_WRITABLE_TYPES.has(f.field_type));

  function updateRow(key: number, patch: Partial<ValueRow>) {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  function removeRow(key: number) {
    setRows((prev) => prev.filter((r) => r.key !== key));
  }

  async function handleSubmit() {
    setError(null);
    try {
      if (actionType === "send_webhook") {
        if (!url.trim()) {
          setError("Give a webhook URL");
          return;
        }
        await createAction.mutateAsync({ action_type: actionType, config: { url: url.trim() } });
      } else {
        if (actionType === "create_record" && !targetTableId) {
          setError("Choose a target table");
          return;
        }
        const filled = rows.filter((r) => r.fieldName && (r.mode === "fixed" ? r.fixedValue !== "" : r.copyFromField));
        if (filled.length === 0) {
          setError("Set at least one field");
          return;
        }
        const values: Record<string, string> = {};
        for (const row of filled) {
          values[row.fieldName] = row.mode === "copy" ? `{{${row.copyFromField}}}` : row.fixedValue;
        }
        const config = actionType === "create_record" ? { target_table_id: targetTableId, values } : { values };
        await createAction.mutateAsync({ action_type: actionType, config });
      }
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not add action"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Add action">
      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Action</label>
        <Select value={actionType} onChange={(e) => setActionType(e.target.value as ActionType)}>
          {ACTION_TYPES.map((type) => (
            <option key={type} value={type} disabled={type === "update_record" && triggerType === "scheduled"}>
              {ACTION_LABELS[type]}
              {type === "update_record" && triggerType === "scheduled" ? " (not available on a schedule)" : ""}
            </option>
          ))}
        </Select>
        {actionType === "update_record" && triggerType === "scheduled" && (
          <p className="mt-1 text-xs text-status-warning">
            A scheduled tick has no single triggering row, so this action isn't available here — use "Create a record" or
            "Send a webhook" instead.
          </p>
        )}
      </div>

      {actionType === "send_webhook" && (
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Webhook URL</label>
          <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/hook" />

          <div className="mt-3 rounded-lg bg-surface-raised p-3">
            <p className="mb-2 text-xs text-ink-secondary">
              When this fires, that URL gets an HTTP <span className="font-medium">POST</span> like this — the
              triggering row's current values, as JSON:
            </p>
            <pre className="overflow-x-auto rounded-md bg-surface p-2.5 font-mono text-[11px] leading-relaxed text-ink-secondary ring-1 ring-inset ring-border-default">
              {JSON.stringify(
                {
                  automation_id: "a1b2c3d4-...",
                  table_id: "e5f6g7h8-...",
                  row_id: 42,
                  values: exampleRowValues(sourceFields),
                },
                null,
                2,
              )}
            </pre>
          </div>
        </div>
      )}

      {actionType === "create_record" && (
        <div className="mb-3">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Target table</label>
          <Select value={targetTableId} onChange={(e) => setTargetTableId(e.target.value)}>
            <option value="">Choose a table…</option>
            {tables?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
        </div>
      )}

      {actionType !== "send_webhook" && (
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">
            Set field values{actionType === "create_record" ? " on the new record" : " on the triggering row"}
          </label>
          {actionType === "create_record" && !targetTableId ? (
            <p className="text-xs text-ink-tertiary">Choose a target table first.</p>
          ) : (
            <div className="space-y-2">
              {rows.map((row) => {
                const targetField = writableFields.find((f) => f.name === row.fieldName);
                return (
                  <div key={row.key} className="flex items-center gap-1.5">
                    <div className="w-32 shrink-0">
                      <Select
                        value={row.fieldName}
                        onChange={(e) => updateRow(row.key, { fieldName: e.target.value, fixedValue: "" })}
                      >
                        <option value="">Field…</option>
                        {writableFields.map((f) => (
                          <option key={f.id} value={f.name}>
                            {f.name}
                          </option>
                        ))}
                      </Select>
                    </div>
                    <span className="shrink-0 text-xs text-ink-tertiary">=</span>
                    <div className="w-28 shrink-0">
                      <Select value={row.mode} onChange={(e) => updateRow(row.key, { mode: e.target.value as ValueRow["mode"] })}>
                        <option value="fixed">Fixed value</option>
                        <option value="copy">Copy field…</option>
                      </Select>
                    </div>
                    {row.mode === "fixed" ? (
                      <FieldValueInput
                        field={targetField}
                        value={row.fixedValue}
                        onChange={(v) => updateRow(row.key, { fixedValue: v })}
                        className="flex-1"
                      />
                    ) : (
                      <div className="flex-1">
                        <Select value={row.copyFromField} onChange={(e) => updateRow(row.key, { copyFromField: e.target.value })}>
                          <option value="">Source field…</option>
                          {sourceFields.map((f) => (
                            <option key={f.id} value={f.name}>
                              {f.name}
                            </option>
                          ))}
                        </Select>
                      </div>
                    )}
                    <button
                      type="button"
                      aria-label="Remove field"
                      className="shrink-0 rounded p-1 text-ink-tertiary hover:bg-status-danger-tint hover:text-status-danger"
                      onClick={() => removeRow(row.key)}
                    >
                      <X className="size-3.5" />
                    </button>
                  </div>
                );
              })}
              <button
                type="button"
                onClick={() => setRows((prev) => [...prev, emptyRow()])}
                className="flex items-center gap-1 text-xs font-medium text-accent-secondary hover:opacity-80"
              >
                <Plus className="size-3.5" /> Add field
              </button>
            </div>
          )}
        </div>
      )}

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
      <Button onClick={handleSubmit} loading={createAction.isPending} className="w-full">
        Add action
      </Button>
    </Dialog>
  );
}
