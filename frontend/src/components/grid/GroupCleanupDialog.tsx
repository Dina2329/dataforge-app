import { useEffect, useState } from "react";
import { usePreviewGroupCleanup, useExecuteGroupCleanup, type GroupCleanupPreview } from "../../hooks/useGroupCleanup";
import { apiErrorMessage } from "../../lib/apiClient";
import type { Field } from "../../types";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Select } from "../ui/Select";

interface GroupCleanupDialogProps {
  tableId: string;
  fields: Field[];
  open: boolean;
  onClose: () => void;
}

/** "Move to missing term": deletes a table's rows wherever every row
 * sharing one group field's value (e.g. a component code) has an empty
 * value field AND a zero score field -- a data point nothing was extracted
 * for at all. A group with even one populated row is left untouched.
 *
 * The three field names are picked fresh each time this opens rather than
 * saved as a per-table config -- this is a one-off cleanup action, not an
 * ongoing feature like Batch Submit/Missing Terms Check, so there's nothing
 * worth persisting. Always requires a preview before the delete button
 * unlocks, same two-step discipline as any other destructive bulk action
 * in this app. */
export function GroupCleanupDialog({ tableId, fields, open, onClose }: GroupCleanupDialogProps) {
  const [groupField, setGroupField] = useState("");
  const [valueField, setValueField] = useState("");
  const [scoreField, setScoreField] = useState("");
  const [preview, setPreview] = useState<GroupCleanupPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const previewCleanup = usePreviewGroupCleanup(tableId);
  const executeCleanup = useExecuteGroupCleanup(tableId);

  useEffect(() => {
    if (!open) return;
    setGroupField(fields[0]?.name ?? "");
    setValueField(fields[0]?.name ?? "");
    setScoreField(fields[0]?.name ?? "");
    setPreview(null);
    setError(null);
  }, [open, fields]);

  function fieldsPicked() {
    return groupField === valueField || groupField === scoreField || valueField === scoreField ? "Pick three different fields" : null;
  }

  async function handlePreview() {
    const conflict = fieldsPicked();
    if (conflict) {
      setError(conflict);
      return;
    }
    setError(null);
    setPreview(null);
    try {
      const result = await previewCleanup.mutateAsync({ group_field: groupField, value_field: valueField, score_field: scoreField });
      setPreview(result);
    } catch (err) {
      setError(apiErrorMessage(err, "Could not preview cleanup"));
    }
  }

  async function handleExecute() {
    if (!preview) return;
    setError(null);
    try {
      await executeCleanup.mutateAsync({ group_field: groupField, value_field: valueField, score_field: scoreField });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not run cleanup"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Move to missing term">
      <p className="mb-4 text-sm text-ink-secondary">
        Finds every group of rows that share the same value in the field below where the value field is empty and the score field is 0
        for <span className="font-medium text-ink-primary">every</span> row in that group, then deletes those rows. A group with even
        one row that doesn't match is left untouched.
      </p>

      <div className="mb-3 grid grid-cols-3 gap-2">
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Group field</label>
          <Select
            value={groupField}
            onChange={(e) => {
              setGroupField(e.target.value);
              setPreview(null);
            }}
          >
            {fields.map((f) => (
              <option key={f.id} value={f.name}>
                {f.name}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Value field</label>
          <Select
            value={valueField}
            onChange={(e) => {
              setValueField(e.target.value);
              setPreview(null);
            }}
          >
            {fields.map((f) => (
              <option key={f.id} value={f.name}>
                {f.name}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Score field</label>
          <Select
            value={scoreField}
            onChange={(e) => {
              setScoreField(e.target.value);
              setPreview(null);
            }}
          >
            {fields.map((f) => (
              <option key={f.id} value={f.name}>
                {f.name}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}

      <Button variant="secondary" onClick={handlePreview} loading={previewCleanup.isPending} className="mb-3 w-full">
        Preview
      </Button>

      {preview && (
        <div className="mb-4 rounded-lg border border-border-default p-3 text-sm">
          {preview.qualifying_groups === 0 ? (
            <p className="text-ink-tertiary">Nothing qualifies -- every group has at least one non-empty value or non-zero score.</p>
          ) : (
            <>
              <p className="mb-1 text-ink-primary">
                <span className="font-medium">{preview.qualifying_groups}</span> data point{preview.qualifying_groups === 1 ? "" : "s"}{" "}
                (<span className="font-medium">{preview.rows_to_delete}</span> row{preview.rows_to_delete === 1 ? "" : "s"}) will be
                deleted.
              </p>
              <p className="truncate text-xs text-ink-tertiary">{preview.sample_group_values.join(", ")}</p>
            </>
          )}
        </div>
      )}

      <Button
        onClick={handleExecute}
        loading={executeCleanup.isPending}
        disabled={!preview || preview.qualifying_groups === 0}
        className="w-full"
      >
        Delete {preview && preview.qualifying_groups > 0 ? `${preview.rows_to_delete} row(s)` : ""}
      </Button>
    </Dialog>
  );
}
