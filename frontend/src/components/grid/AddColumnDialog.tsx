import { useEffect, useState } from "react";
import { FIELD_TYPES, ROLLUP_AGGREGATES, type Field, type FieldTypeKey, type RollupAggregate } from "../../types";
import { useCreateField, useTable } from "../../hooks/useBases";
import { useWorkspaceTables } from "../../hooks/useDashboards";
import { apiErrorMessage } from "../../lib/apiClient";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

const FIELD_TYPE_LABELS: Record<FieldTypeKey, string> = {
  text: "Single line text",
  long_text: "Long text",
  number: "Number",
  boolean: "Checkbox",
  date: "Date",
  single_select: "Single select",
  link_to_record: "Link to another table",
  lookup: "Lookup",
  rollup: "Rollup",
  formula: "Formula",
  attachment: "Attachment",
};

interface AddColumnDialogProps {
  tableId: string;
  workspaceId: string | undefined;
  fields: Field[];
  open: boolean;
  onClose: () => void;
}

export function AddColumnDialog({ tableId, workspaceId, fields, open, onClose }: AddColumnDialogProps) {
  const createField = useCreateField(tableId);
  const { data: workspaceTables } = useWorkspaceTables(open ? workspaceId : undefined);
  const [name, setName] = useState("");
  const [fieldType, setFieldType] = useState<FieldTypeKey>("text");
  const [choicesText, setChoicesText] = useState("");
  const [targetTableId, setTargetTableId] = useState("");
  const [linkFieldId, setLinkFieldId] = useState("");
  const [targetFieldId, setTargetFieldId] = useState("");
  const [aggregate, setAggregate] = useState<RollupAggregate>("count");
  const [expression, setExpression] = useState("");
  const [error, setError] = useState<string | null>(null);

  const linkFields = fields.filter((f) => f.field_type === "link_to_record");
  const selectedLinkField = linkFields.find((f) => f.id === linkFieldId);
  const { data: linkTargetTable } = useTable(selectedLinkField?.options.target_table_id);

  useEffect(() => {
    if (!open) return;
    setName("");
    setFieldType("text");
    setChoicesText("");
    setTargetTableId("");
    setLinkFieldId(linkFields[0]?.id ?? "");
    setTargetFieldId("");
    setAggregate("count");
    setExpression("");
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function handleSubmit() {
    if (!name.trim()) {
      setError("Give the field a name");
      return;
    }
    setError(null);

    let options: Record<string, unknown> = {};
    if (fieldType === "single_select") {
      options = {
        choices: choicesText
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean)
          .map((c) => ({ value: c, label: c })),
      };
    } else if (fieldType === "link_to_record") {
      if (!targetTableId) {
        setError("Choose a table to link to");
        return;
      }
      options = { target_table_id: targetTableId };
    } else if (fieldType === "lookup" || fieldType === "rollup") {
      if (!linkFieldId || !targetFieldId) {
        setError("Choose a link field and a field to pull from");
        return;
      }
      options = fieldType === "rollup" ? { link_field_id: linkFieldId, target_field_id: targetFieldId, aggregate } : { link_field_id: linkFieldId, target_field_id: targetFieldId };
    } else if (fieldType === "formula") {
      if (!expression.trim()) {
        setError("Write a formula expression");
        return;
      }
      options = { expression: expression.trim() };
    }

    try {
      await createField.mutateAsync({ name: name.trim(), field_type: fieldType, options });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not create field"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Add field">
      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Field name</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Status" />
      </div>
      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Field type</label>
        <Select value={fieldType} onChange={(e) => setFieldType(e.target.value as FieldTypeKey)}>
          {FIELD_TYPES.map((type) => (
            <option key={type} value={type}>
              {FIELD_TYPE_LABELS[type]}
            </option>
          ))}
        </Select>
      </div>

      {fieldType === "single_select" && (
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Choices (comma separated)</label>
          <Input value={choicesText} onChange={(e) => setChoicesText(e.target.value)} placeholder="Todo, In progress, Done" />
        </div>
      )}

      {fieldType === "link_to_record" && (
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Link to table</label>
          <Select value={targetTableId} onChange={(e) => setTargetTableId(e.target.value)}>
            <option value="">Choose a table…</option>
            {workspaceTables?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
        </div>
      )}

      {(fieldType === "lookup" || fieldType === "rollup") && (
        <>
          {linkFields.length === 0 ? (
            <p className="mb-4 text-xs text-status-warning">
              This table has no "Link to another table" field yet — add one first.
            </p>
          ) : (
            <>
              <div className="mb-3">
                <label className="mb-1 block text-xs font-medium text-ink-secondary">Through link field</label>
                <Select
                  value={linkFieldId}
                  onChange={(e) => {
                    setLinkFieldId(e.target.value);
                    setTargetFieldId("");
                  }}
                >
                  {linkFields.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="mb-3">
                <label className="mb-1 block text-xs font-medium text-ink-secondary">
                  {fieldType === "rollup" ? "Field to aggregate" : "Field to pull in"}
                </label>
                <Select value={targetFieldId} onChange={(e) => setTargetFieldId(e.target.value)}>
                  <option value="">Choose a field…</option>
                  {linkTargetTable?.fields
                    .filter((f) => !["link_to_record", "lookup", "rollup", "formula", "attachment"].includes(f.field_type))
                    .map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                </Select>
              </div>
              {fieldType === "rollup" && (
                <div className="mb-4">
                  <label className="mb-1 block text-xs font-medium text-ink-secondary">Aggregate</label>
                  <Select value={aggregate} onChange={(e) => setAggregate(e.target.value as RollupAggregate)}>
                    {ROLLUP_AGGREGATES.map((agg) => (
                      <option key={agg} value={agg}>
                        {agg}
                      </option>
                    ))}
                  </Select>
                </div>
              )}
            </>
          )}
        </>
      )}

      {fieldType === "formula" && (
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

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
      <Button
        onClick={handleSubmit}
        loading={createField.isPending}
        disabled={(fieldType === "lookup" || fieldType === "rollup") && linkFields.length === 0}
        className="w-full"
      >
        Add field
      </Button>
    </Dialog>
  );
}
