import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FILTER_OPERATORS, type Field, type FilterCondition, type FilterOperator } from "../../types";
import { useExecuteBulkUpdate, useBulkOperationStatus, usePreviewBulkUpdate, useUndoBulkOperation } from "../../hooks/useBulkOps";
import { invalidateRecordsQueries } from "../../hooks/useRecords";
import { apiErrorMessage } from "../../lib/apiClient";
import { coerceForField, NO_VALUE_OPERATORS, OPERATOR_LABELS } from "../../lib/filterHelpers";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Select } from "../ui/Select";
import { FieldValueInput } from "../shared/FieldValueInput";

interface BulkUpdateDialogProps {
  tableId: string;
  fields: Field[];
  open: boolean;
  onClose: () => void;
}

export function BulkUpdateDialog({ tableId, fields, open, onClose }: BulkUpdateDialogProps) {
  const filterableFields = fields;
  const updatableFields = useMemo(() => fields.filter((f) => !f.is_primary), [fields]);

  const [filterFieldName, setFilterFieldName] = useState(filterableFields[0]?.name ?? "");
  const [operator, setOperator] = useState<FilterOperator>("eq");
  const [filterValueRaw, setFilterValueRaw] = useState("");

  const [setFieldName, setSetFieldName] = useState(updatableFields[0]?.name ?? "");
  const [setValueRaw, setSetValueRaw] = useState("");

  const [operationId, setOperationId] = useState<string | null>(null);
  const [awaitingUndo, setAwaitingUndo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const preview = usePreviewBulkUpdate(tableId);
  const execute = useExecuteBulkUpdate(tableId);
  const undo = useUndoBulkOperation(tableId);
  const { data: operationStatus } = useBulkOperationStatus(operationId ?? undefined, !!operationId, awaitingUndo);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (operationStatus?.status === "completed" || operationStatus?.undone_at) {
      invalidateRecordsQueries(queryClient, tableId);
    }
  }, [operationStatus?.status, operationStatus?.undone_at, queryClient, tableId]);

  const filterField = filterableFields.find((f) => f.name === filterFieldName);
  const setField = updatableFields.find((f) => f.name === setFieldName);

  function buildFilter(): FilterCondition {
    return {
      kind: "condition",
      field: filterFieldName,
      operator,
      value: NO_VALUE_OPERATORS.has(operator) ? undefined : coerceForField(filterField, filterValueRaw),
    };
  }

  function buildValues(): Record<string, unknown> {
    return { [setFieldName]: coerceForField(setField, setValueRaw) };
  }

  function reset() {
    setOperationId(null);
    setAwaitingUndo(false);
    preview.reset();
    setError(null);
  }

  async function handlePreview() {
    setError(null);
    try {
      await preview.mutateAsync({ filter: buildFilter(), values: buildValues() });
    } catch (err) {
      setError(apiErrorMessage(err, "Preview failed"));
    }
  }

  async function handleExecute() {
    setError(null);
    try {
      const operation = await execute.mutateAsync({ filter: buildFilter(), values: buildValues() });
      setOperationId(operation.id);
    } catch (err) {
      setError(apiErrorMessage(err, "Bulk update failed"));
    }
  }

  async function handleUndo() {
    if (!operationId) return;
    setAwaitingUndo(true);
    try {
      await undo.mutateAsync(operationId);
    } catch (err) {
      setAwaitingUndo(false);
      setError(apiErrorMessage(err, "Undo failed"));
    }
  }

  return (
    <Dialog
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="Bulk update"
    >
      <p className="mb-2 text-xs font-medium text-ink-secondary">Where</p>
      <div className="mb-4 flex gap-2">
        <div className="flex-1">
          <Select value={filterFieldName} onChange={(e) => setFilterFieldName(e.target.value)}>
            {filterableFields.map((f) => (
              <option key={f.id} value={f.name}>
                {f.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex-1">
          <Select value={operator} onChange={(e) => setOperator(e.target.value as FilterOperator)}>
            {FILTER_OPERATORS.map((op) => (
              <option key={op} value={op}>
                {OPERATOR_LABELS[op]}
              </option>
            ))}
          </Select>
        </div>
        {!NO_VALUE_OPERATORS.has(operator) && (
          <FieldValueInput field={filterField} value={filterValueRaw} onChange={setFilterValueRaw} className="flex-1" />
        )}
      </div>

      <p className="mb-2 text-xs font-medium text-ink-secondary">Set</p>
      <div className="mb-4 flex gap-2">
        <div className="flex-1">
          <Select value={setFieldName} onChange={(e) => setSetFieldName(e.target.value)}>
            {updatableFields.map((f) => (
              <option key={f.id} value={f.name}>
                {f.name}
              </option>
            ))}
          </Select>
        </div>
        <FieldValueInput field={setField} value={setValueRaw} onChange={setSetValueRaw} className="flex-1" />
      </div>

      {preview.data && !operationId && (
        <div className="mb-4 rounded-md bg-surface-raised p-3 text-sm">
          <p className="font-medium text-ink-secondary">{preview.data.matched_count} row(s) match</p>
          {preview.data.sample_rows.length > 0 && (
            <ul className="mt-1 max-h-32 overflow-auto text-xs text-ink-tertiary">
              {preview.data.sample_rows.map((row) => (
                <li key={row.row_id}>#{row.row_id}: {JSON.stringify(row.values)}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {operationId && operationStatus && (
        <div className="mb-4 rounded-lg bg-surface-raised p-3 text-sm">
          <p className="font-medium text-ink-secondary">Status: {operationStatus.status}</p>
          {operationStatus.status === "completed" && (
            <p className="text-ink-tertiary">
              {operationStatus.affected_count} row(s) updated.{" "}
              {operationStatus.undone_at ? "Undone." : (
                <button className="font-medium text-accent-secondary hover:underline" onClick={handleUndo} disabled={undo.isPending}>
                  {undo.isPending ? "Undoing…" : "Undo"}
                </button>
              )}
            </p>
          )}
          {operationStatus.status === "failed" && <p className="text-status-danger">{operationStatus.error}</p>}
        </div>
      )}

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}

      {!operationId ? (
        <div className="flex gap-2">
          <Button variant="secondary" loading={preview.isPending} onClick={handlePreview} className="flex-1">
            Preview
          </Button>
          <Button loading={execute.isPending} disabled={!preview.data} onClick={handleExecute} className="flex-1">
            Execute
          </Button>
        </div>
      ) : (
        <Button variant="secondary" onClick={reset} className="w-full">
          Run another
        </Button>
      )}
    </Dialog>
  );
}
