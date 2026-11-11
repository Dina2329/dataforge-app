import { useState } from "react";
import { useCreateAutomation } from "../../hooks/useAutomations";
import { apiErrorMessage } from "../../lib/apiClient";
import { FILTER_OPERATORS, TRIGGER_TYPES, type Field, type FilterOperator, type TriggerType } from "../../types";
import { NO_VALUE_OPERATORS } from "../../lib/filterHelpers";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";
import { FieldValueInput } from "../shared/FieldValueInput";

const TRIGGER_LABELS: Record<TriggerType, string> = {
  record_created: "When a record is created",
  record_updated: "When a record is updated",
  scheduled: "On a schedule",
};

// watched_fields only makes sense against a prior state to diff -- a
// link_to_record/lookup/rollup/formula field never appears in a write's own
// values (it's resolved separately, never written directly), so it could
// never actually be "changed" in the sense this checks.
const NON_WATCHABLE_TYPES = new Set(["link_to_record", "lookup", "rollup", "formula", "attachment"]);

interface CreateAutomationDialogProps {
  tableId: string;
  fields: Field[];
  open: boolean;
  onClose: () => void;
}

export function CreateAutomationDialog({ tableId, fields, open, onClose }: CreateAutomationDialogProps) {
  const createAutomation = useCreateAutomation(tableId);
  const [name, setName] = useState("");
  const [triggerType, setTriggerType] = useState<TriggerType>("record_updated");
  const [filterField, setFilterField] = useState("");
  const [filterOperator, setFilterOperator] = useState<FilterOperator>("eq");
  const [filterValue, setFilterValue] = useState("");
  const [watchedFields, setWatchedFields] = useState<string[]>([]);
  const [cron, setCron] = useState("*/5 * * * *");
  const [error, setError] = useState<string | null>(null);

  const watchableFields = fields.filter((f) => !NON_WATCHABLE_TYPES.has(f.field_type));

  function toggleWatchedField(name: string) {
    setWatchedFields((prev) => (prev.includes(name) ? prev.filter((f) => f !== name) : [...prev, name]));
  }

  function reset() {
    setName("");
    setTriggerType("record_updated");
    setFilterField("");
    setFilterValue("");
    setWatchedFields([]);
    setError(null);
  }

  async function handleSubmit() {
    if (!name.trim()) {
      setError("Give the automation a name");
      return;
    }
    if (triggerType === "scheduled" && !cron.trim()) {
      setError("Give a cron expression");
      return;
    }
    setError(null);
    const trigger_config =
      triggerType === "scheduled"
        ? { cron: cron.trim() }
        : {
            ...(filterField ? { filter: { kind: "condition" as const, field: filterField, operator: filterOperator, value: filterValue } } : {}),
            ...(triggerType === "record_updated" && watchedFields.length > 0 ? { watched_fields: watchedFields } : {}),
          };
    try {
      await createAutomation.mutateAsync({ name: name.trim(), trigger_type: triggerType, trigger_config });
      reset();
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not create automation"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="New automation">
      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Name</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Notify on completion" />
      </div>
      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Trigger</label>
        <Select value={triggerType} onChange={(e) => setTriggerType(e.target.value as TriggerType)}>
          {TRIGGER_TYPES.map((type) => (
            <option key={type} value={type}>
              {TRIGGER_LABELS[type]}
            </option>
          ))}
        </Select>
      </div>

      {triggerType === "scheduled" ? (
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Cron expression</label>
          <Input value={cron} onChange={(e) => setCron(e.target.value)} placeholder="*/5 * * * *" />
        </div>
      ) : (
        <div className="mb-4 space-y-2 rounded-lg bg-surface-raised p-3">
          <p className="text-xs font-medium text-ink-secondary">Only run when (optional)</p>
          <div className="grid grid-cols-3 gap-2">
            <Select value={filterField} onChange={(e) => setFilterField(e.target.value)}>
              <option value="">Any change</option>
              {fields.map((f) => (
                <option key={f.id} value={f.name}>
                  {f.name}
                </option>
              ))}
            </Select>
            <Select value={filterOperator} onChange={(e) => setFilterOperator(e.target.value as FilterOperator)} disabled={!filterField}>
              {FILTER_OPERATORS.map((op) => (
                <option key={op} value={op}>
                  {op}
                </option>
              ))}
            </Select>
            {!NO_VALUE_OPERATORS.has(filterOperator) && (
              <FieldValueInput
                field={fields.find((f) => f.name === filterField)}
                value={filterValue}
                onChange={setFilterValue}
                disabled={!filterField}
              />
            )}
          </div>
        </div>
      )}

      {triggerType === "record_updated" && (
        <div className="mb-4 space-y-2 rounded-lg bg-surface-raised p-3">
          <p className="text-xs font-medium text-ink-secondary">Only when these columns change (optional)</p>
          <p className="text-xs text-ink-tertiary">Leave all unchecked to run on any column changing.</p>
          <div className="grid max-h-40 grid-cols-2 gap-x-3 gap-y-1 overflow-y-auto">
            {watchableFields.map((f) => (
              <label key={f.id} className="flex items-center gap-1.5 text-sm text-ink-secondary">
                <input
                  type="checkbox"
                  checked={watchedFields.includes(f.name)}
                  onChange={() => toggleWatchedField(f.name)}
                  className="accent-accent-secondary"
                />
                {f.name}
              </label>
            ))}
          </div>
        </div>
      )}

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
      <Button onClick={handleSubmit} loading={createAutomation.isPending} className="w-full">
        Create automation
      </Button>
    </Dialog>
  );
}
