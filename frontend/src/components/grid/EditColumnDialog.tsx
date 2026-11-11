import { useEffect, useState } from "react";
import type { Field } from "../../types";
import { useTable, useUpdateField } from "../../hooks/useBases";
import { useWorkspaceTables } from "../../hooks/useDashboards";
import { apiErrorMessage } from "../../lib/apiClient";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

// Same ineligible set GridFilterDialog.tsx already excludes from filtering --
// these have no real column to compare values against (or, for attachment,
// no sensible notion of "already used").
const NON_EXCLUDABLE_TYPES = new Set(["link_to_record", "lookup", "rollup", "formula", "attachment"]);

interface EditColumnDialogProps {
  tableId: string;
  workspaceId: string | undefined;
  field: Field | null;
  onClose: () => void;
}

// Only name/required are editable for every field type -- a field's type and
// its structural options (link target, rollup source, ...) are fixed at
// creation, since changing them would mean migrating already-stored data or
// dangling references from other fields. single_select's choices and
// formula's expression are the two exceptions: genuinely user-facing config
// that's safe to revise in place (matches what BasesService.update_field
// actually accepts).
export function EditColumnDialog({ tableId, workspaceId, field, onClose }: EditColumnDialogProps) {
  const updateField = useUpdateField(tableId);
  const [name, setName] = useState("");
  const [required, setRequired] = useState(false);
  const [choicesText, setChoicesText] = useState("");
  const [expression, setExpression] = useState("");
  const [excludeTableId, setExcludeTableId] = useState("");
  const [excludeFieldId, setExcludeFieldId] = useState("");
  const [excludeSectionOpen, setExcludeSectionOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Gated on the dialog actually being open -- same pattern as
  // AddColumnDialog's own useWorkspaceTables(open ? ... : undefined).
  // Unconditional here would fan out one request per base plus one per
  // table in the whole workspace on every single grid page load (this
  // dialog is always mounted, just normally closed), not only when someone
  // opens "Edit field."
  const { data: workspaceTables } = useWorkspaceTables(field ? workspaceId : undefined);
  const { data: excludeTargetTable } = useTable(field && excludeTableId ? excludeTableId : undefined);

  useEffect(() => {
    if (!field) return;
    setName(field.name);
    setRequired(field.required);
    setChoicesText(((field.options.choices as { label: string }[] | undefined) ?? []).map((c) => c.label).join(", "));
    setExpression((field.options.expression as string | undefined) ?? "");
    setExcludeTableId(field.options.exclude_values_from?.table_id ?? "");
    setExcludeFieldId(field.options.exclude_values_from?.field_id ?? "");
    // Open by default whenever a mapping is already configured -- otherwise
    // editing a field that already excludes values would silently hide that
    // fact behind a collapsed section, making it look unset until the user
    // happens to expand it themselves.
    setExcludeSectionOpen(!!field.options.exclude_values_from);
    setError(null);
  }, [field]);

  if (!field) return null;
  const canExclude = !NON_EXCLUDABLE_TYPES.has(field.field_type);

  async function handleSubmit() {
    if (!field) return;
    if (!name.trim()) {
      setError("Give the field a name");
      return;
    }
    setError(null);

    const payload: { fieldId: string; name?: string; required?: boolean; options?: object } = {
      fieldId: field.id,
      name: name.trim(),
      required,
    };
    if (field.field_type === "single_select") {
      payload.options = {
        choices: choicesText
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean)
          .map((c) => ({ value: c, label: c })),
      };
    } else if (field.field_type === "formula") {
      if (!expression.trim()) {
        setError("Write a formula expression");
        return;
      }
      payload.options = { expression: expression.trim() };
    }

    if (canExclude) {
      payload.options = {
        ...(payload.options ?? {}),
        exclude_values_from: excludeTableId && excludeFieldId ? { table_id: excludeTableId, field_id: excludeFieldId } : null,
      };
    }

    try {
      await updateField.mutateAsync(payload);
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not update field"));
    }
  }

  return (
    <Dialog open={field !== null} onClose={onClose} title="Edit field">
      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Field name</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Status" />
      </div>

      {!field.is_primary && (
        <label className="mb-3 flex items-center gap-2 text-sm text-ink-secondary">
          <input
            type="checkbox"
            checked={required}
            onChange={(e) => setRequired(e.target.checked)}
            className="accent-accent-secondary"
          />
          Required
        </label>
      )}

      {field.field_type === "single_select" && (
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Choices (comma separated)</label>
          <Input value={choicesText} onChange={(e) => setChoicesText(e.target.value)} placeholder="Todo, In progress, Done" />
        </div>
      )}

      {field.field_type === "formula" && (
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">
            Expression — reference fields as <code>{"{Field Name}"}</code>
          </label>
          <textarea
            value={expression}
            onChange={(e) => setExpression(e.target.value)}
            rows={3}
            placeholder='{Price} * {Quantity}, or concat({First}, " ", {Last})'
            className="w-full rounded-lg border border-border-default bg-surface px-3 py-2 font-mono text-xs text-ink-primary outline-none transition-colors focus:border-accent-secondary focus:ring-2 focus:ring-accent-secondary/30"
          />
        </div>
      )}

      {canExclude && (
        <details
          open={excludeSectionOpen}
          onToggle={(e) => setExcludeSectionOpen(e.currentTarget.open)}
          className="mb-4 rounded-lg border border-border-default px-3 py-2"
        >
          <summary className="cursor-pointer text-xs font-medium text-ink-secondary">
            Exclude values already used in…
            {excludeTableId && excludeFieldId && !excludeSectionOpen && (
              <span className="ml-1 font-normal text-ink-tertiary">(configured)</span>
            )}
          </summary>
          <div className="mt-3 space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-ink-secondary">Table</label>
              <Select
                value={excludeTableId}
                onChange={(e) => {
                  setExcludeTableId(e.target.value);
                  setExcludeFieldId("");
                }}
              >
                <option value="">None</option>
                {workspaceTables?.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </div>
            {excludeTableId && (
              <div>
                <label className="mb-1 block text-xs font-medium text-ink-secondary">Field</label>
                <Select value={excludeFieldId} onChange={(e) => setExcludeFieldId(e.target.value)}>
                  <option value="">Choose a field…</option>
                  {excludeTargetTable?.fields
                    .filter((f) => !NON_EXCLUDABLE_TYPES.has(f.field_type))
                    .map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                </Select>
              </div>
            )}
            <p className="text-xs text-ink-tertiary">
              When filtering this field, only values not already used in the chosen field will be suggested. Rows are never hidden.
            </p>
          </div>
        </details>
      )}

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
      <Button onClick={handleSubmit} loading={updateField.isPending} className="w-full">
        Save changes
      </Button>
    </Dialog>
  );
}
