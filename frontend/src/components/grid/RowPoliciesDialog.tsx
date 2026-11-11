import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useMembers } from "../../hooks/useMembers";
import { useDeleteRowPolicy, useRowPolicies, useSetRowPolicy } from "../../hooks/useRowPolicies";
import { apiErrorMessage } from "../../lib/apiClient";
import { FILTER_OPERATORS, type Field, type FilterOperator } from "../../types";
import { NO_VALUE_OPERATORS } from "../../lib/filterHelpers";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Select } from "../ui/Select";
import { FieldValueInput } from "../shared/FieldValueInput";

interface RowPoliciesDialogProps {
  tableId: string;
  workspaceId: string | undefined;
  fields: Field[];
  open: boolean;
  onClose: () => void;
}

export function RowPoliciesDialog({ tableId, workspaceId, fields, open, onClose }: RowPoliciesDialogProps) {
  const { data: members } = useMembers(workspaceId);
  const { data: policies, isError, error } = useRowPolicies(open ? tableId : undefined);
  const setPolicy = useSetRowPolicy(tableId);
  const deletePolicy = useDeleteRowPolicy(tableId);

  const filterableFields = fields.filter((f) => !["link_to_record", "lookup", "rollup", "formula", "attachment"].includes(f.field_type));

  const [targetUserId, setTargetUserId] = useState("");
  const [field, setField] = useState("");
  const [operator, setOperator] = useState<FilterOperator>("eq");
  const [value, setValue] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSave() {
    if (!targetUserId || !field) {
      setFormError("Choose a member and a field");
      return;
    }
    setFormError(null);
    try {
      await setPolicy.mutateAsync({
        targetUserId,
        filter: { kind: "condition", field, operator, value: NO_VALUE_OPERATORS.has(operator) ? undefined : value },
      });
      setTargetUserId("");
      setField("");
      setValue("");
    } catch (err) {
      setFormError(apiErrorMessage(err, "Could not save the policy"));
    }
  }

  function memberEmail(userId: string): string {
    return members?.find((m) => m.user_id === userId)?.email ?? userId;
  }

  return (
    <Dialog open={open} onClose={onClose} title="Row-level access">
      <p className="mb-4 text-sm text-ink-secondary">
        Scope a member's visibility on this table to rows matching a condition. Owners and admins always see every row.
      </p>

      {isError ? (
        <p className="mb-4 text-sm text-status-danger">{apiErrorMessage(error, "You don't have permission to manage row-level access.")}</p>
      ) : (
        <>
          <div className="mb-4 space-y-1.5">
            {policies?.length ? (
              policies.map((policy) => (
                <div key={policy.id} className="flex items-center justify-between rounded-lg bg-surface-raised px-3 py-2 text-xs">
                  <span>
                    <span className="font-medium text-ink-secondary">{memberEmail(policy.user_id)}</span>
                    <span className="text-ink-tertiary">
                      {" "}
                      · sees only where {policy.filter.field} {policy.filter.operator} "{String(policy.filter.value)}"
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() => deletePolicy.mutate(policy.id)}
                    className="text-ink-tertiary hover:text-status-danger"
                    aria-label="Remove policy"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))
            ) : (
              <p className="text-xs text-ink-tertiary">No row-level scopes on this table yet — every member sees every row.</p>
            )}
          </div>

          <div className="space-y-2 rounded-lg bg-surface-raised p-3">
            <p className="text-xs font-medium text-ink-secondary">Add a scope</p>
            <Select value={targetUserId} onChange={(e) => setTargetUserId(e.target.value)}>
              <option value="">Choose a member…</option>
              {members?.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.email} ({m.role})
                </option>
              ))}
            </Select>
            <div className="grid grid-cols-3 gap-2">
              <Select value={field} onChange={(e) => setField(e.target.value)}>
                <option value="">Field…</option>
                {filterableFields.map((f) => (
                  <option key={f.id} value={f.name}>
                    {f.name}
                  </option>
                ))}
              </Select>
              <Select value={operator} onChange={(e) => setOperator(e.target.value as FilterOperator)}>
                {FILTER_OPERATORS.map((op) => (
                  <option key={op} value={op}>
                    {op}
                  </option>
                ))}
              </Select>
              {!NO_VALUE_OPERATORS.has(operator) && (
                <FieldValueInput field={filterableFields.find((f) => f.name === field)} value={value} onChange={setValue} />
              )}
            </div>
            {formError && <p className="text-sm text-status-danger">{formError}</p>}
            <Button className="w-full" loading={setPolicy.isPending} onClick={handleSave}>
              Save scope
            </Button>
          </div>
        </>
      )}
    </Dialog>
  );
}
