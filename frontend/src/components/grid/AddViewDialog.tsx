import { useEffect, useState } from "react";
import { useCreateView } from "../../hooks/useBases";
import { apiErrorMessage } from "../../lib/apiClient";
import { VIEW_TYPES, type Field, type ViewType } from "../../types";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

const VIEW_TYPE_LABELS: Record<ViewType, string> = {
  grid: "Grid",
  kanban: "Kanban board",
  form: "Form (shareable, for collecting new rows)",
};

interface AddViewDialogProps {
  tableId: string;
  fields: Field[];
  open: boolean;
  onClose: () => void;
  onCreated: (viewId: string) => void;
}

export function AddViewDialog({ tableId, fields, open, onClose, onCreated }: AddViewDialogProps) {
  const createView = useCreateView(tableId);
  const singleSelectFields = fields.filter((f) => f.field_type === "single_select");

  const [name, setName] = useState("");
  const [viewType, setViewType] = useState<ViewType>("kanban");
  const [groupFieldId, setGroupFieldId] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName("");
    setViewType("kanban");
    setGroupFieldId(singleSelectFields[0]?.id ?? "");
    setDescription("");
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function handleSubmit() {
    if (!name.trim()) {
      setError("Give the view a name");
      return;
    }
    if (viewType === "kanban" && !groupFieldId) {
      setError("Choose a single-select field to group cards by");
      return;
    }
    setError(null);
    try {
      const config =
        viewType === "kanban"
          ? { group_field_id: groupFieldId }
          : viewType === "form"
            ? { description: description.trim() || undefined }
            : {};
      const view = await createView.mutateAsync({ name: name.trim(), view_type: viewType, config });
      onCreated(view.id);
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not create view"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Add view">
      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">View name</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Board" />
      </div>
      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Type</label>
        <Select value={viewType} onChange={(e) => setViewType(e.target.value as ViewType)}>
          {VIEW_TYPES.map((type) => (
            <option key={type} value={type}>
              {VIEW_TYPE_LABELS[type]}
            </option>
          ))}
        </Select>
      </div>

      {viewType === "kanban" && (
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Group cards by</label>
          {singleSelectFields.length === 0 ? (
            <p className="text-xs text-status-warning">This table has no single-select field yet — add one first.</p>
          ) : (
            <Select value={groupFieldId} onChange={(e) => setGroupFieldId(e.target.value)}>
              {singleSelectFields.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </Select>
          )}
        </div>
      )}

      {viewType === "form" && (
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Description (optional)</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            placeholder="Shown at the top of the form"
            className="w-full rounded-lg border border-border-default bg-surface px-3 py-2 text-sm text-ink-primary outline-none transition-colors focus:border-accent-secondary focus:ring-2 focus:ring-accent-secondary/30"
          />
          <p className="mt-1 text-xs text-ink-tertiary">Every field on this table will be included on the form.</p>
        </div>
      )}

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
      <Button
        onClick={handleSubmit}
        loading={createView.isPending}
        disabled={viewType === "kanban" && singleSelectFields.length === 0}
        className="w-full"
      >
        Add view
      </Button>
    </Dialog>
  );
}
