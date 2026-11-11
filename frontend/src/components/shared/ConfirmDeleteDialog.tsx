import { AlertTriangle } from "lucide-react";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";

interface ConfirmDeleteDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  loading?: boolean;
  /** Not every irreversible-ish confirmation is a delete (e.g. "Restore") --
   * defaults to "Delete" so every existing call site is unaffected. */
  confirmLabel?: string;
}

export function ConfirmDeleteDialog({ open, onClose, onConfirm, title, description, loading, confirmLabel = "Delete" }: ConfirmDeleteDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} title={title}>
      <div className="mb-4 flex gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-status-danger-tint">
          <AlertTriangle className="size-4 text-status-danger" />
        </div>
        <p className="text-sm text-ink-secondary">{description}</p>
      </div>
      <div className="flex gap-2">
        <Button variant="secondary" onClick={onClose} className="flex-1">
          Cancel
        </Button>
        <Button variant="danger" onClick={onConfirm} loading={loading} className="flex-1">
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
