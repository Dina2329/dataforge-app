import { useState } from "react";
import { ArrowLeft, Check, PlusCircle, RefreshCw, Send, ShieldCheck, Trash2, X } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import {
  useApproveSyncChangeBatch,
  useDraftSyncChanges,
  useRejectSyncChangeBatch,
  useSubmitSyncChangeDrafts,
  useSyncChangeBatches,
} from "../hooks/useDataSources";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import type { PendingSyncChange, SyncChangeBatch } from "../types";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { Input } from "../components/ui/Input";
import { PageHeader } from "../components/shared/PageHeader";
import { EmptyState } from "../components/shared/EmptyState";
import { ListRowsSkeleton } from "../components/ui/Skeleton";

const OPERATION_ICON = { insert: PlusCircle, update: RefreshCw, delete: Trash2 } as const;
const OPERATION_TONE = { insert: "success", update: "info", delete: "danger" } as const;

function ChangeRow({ change }: { change: PendingSyncChange }) {
  const Icon = OPERATION_ICON[change.operation];
  return (
    <div className="flex items-start gap-3 py-2">
      <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-accent-secondary-tint">
        <Icon className="size-3.5 text-accent-secondary" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium text-ink-primary">{change.table_name}</p>
          <Badge tone={OPERATION_TONE[change.operation]}>{change.operation}</Badge>
        </div>
        {change.operation === "delete" ? (
          <p className="mt-0.5 text-xs text-ink-tertiary">Removes row #{change.row_id} from the source (external id {change.external_pk}).</p>
        ) : (
          <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-tertiary">
            {Object.entries(change.values ?? {})
              .slice(0, 6)
              .map(([key, value]) => (
                <span key={key}>
                  <span className="text-ink-secondary">{key}:</span> {value === null || value === "" ? "—" : String(value)}
                </span>
              ))}
            {Object.keys(change.values ?? {}).length > 6 && <span>+{Object.keys(change.values ?? {}).length - 6} more</span>}
          </div>
        )}
      </div>
    </div>
  );
}

const RESTORE_LABEL = {
  insert: "new row(s) deleted",
  update: "edited value(s) reverted",
  delete: "deleted row(s) brought back",
} as const;

function restoreSummary(changes: PendingSyncChange[]): string {
  const ops = Array.from(new Set(changes.map((c) => c.operation)));
  return ops.map((op) => RESTORE_LABEL[op]).join(", ");
}

function RejectDialog({ batch, onClose }: { batch: SyncChangeBatch | null; onClose: () => void }) {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const reject = useRejectSyncChangeBatch(workspaceId);
  const [reason, setReason] = useState("");
  const [restore, setRestore] = useState(false);

  if (!batch) return null;
  // Only meaningful where there's a "before" to go back to -- an insert
  // never had one (restoring it just deletes the row instead), so it never
  // blocks the checkbox; update/delete rows from before this feature
  // shipped have none recorded, so those do block it.
  const canRestore = batch.changes.every((c) => c.operation === "insert" || c.previous_values !== null);
  return (
    <Dialog open title="Reject batch" onClose={onClose}>
      <p className="mb-3 text-sm text-ink-secondary">
        These {batch.changes.length} change{batch.changes.length === 1 ? "" : "s"} from{" "}
        <span className="font-medium text-ink-primary">{batch.requested_by_name}</span> will not be pushed to their source. They'll be
        notified.
      </p>
      <Input
        placeholder="Reason (optional)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        autoFocus
        className="mb-3"
      />
      <label className="mb-4 flex items-start gap-2 text-sm text-ink-secondary">
        <input
          type="checkbox"
          checked={restore}
          disabled={!canRestore}
          onChange={(e) => setRestore(e.target.checked)}
          className="mt-0.5"
        />
        <span>
          Also revert these changes locally ({restoreSummary(batch.changes)})
          {!canRestore && " (unavailable — one or more of these changes predates the restore feature)"}
        </span>
      </label>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="danger"
          loading={reject.isPending}
          onClick={() => reject.mutate({ batchId: batch.id, reason: reason.trim() || null, restore }, { onSuccess: onClose })}
        >
          Reject
        </Button>
      </div>
    </Dialog>
  );
}

function YourDrafts({ workspaceId }: { workspaceId: string | undefined }) {
  const { data: drafts, isLoading } = useDraftSyncChanges(workspaceId);
  const submit = useSubmitSyncChangeDrafts(workspaceId);

  if (isLoading || !drafts?.length) return null;
  return (
    <Card className="mb-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-ink-primary">Your unsubmitted edits ({drafts.length})</p>
          <p className="text-xs text-ink-tertiary">Nothing here is visible to an approver until you submit it.</p>
        </div>
        <Button size="sm" loading={submit.isPending} onClick={() => submit.mutate()}>
          <Send className="size-3.5" /> Submit for approval
        </Button>
      </div>
      <div className="mt-2 divide-y divide-border">
        {drafts.map((change) => (
          <ChangeRow key={change.id} change={change} />
        ))}
      </div>
    </Card>
  );
}

export function PendingSyncChangesPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  useReportWorkspaceContext(workspaceId);
  const { data: batches, isLoading, isError } = useSyncChangeBatches(workspaceId);
  const approve = useApproveSyncChangeBatch(workspaceId);
  const [rejecting, setRejecting] = useState<SyncChangeBatch | null>(null);

  return (
    <div className="mx-auto max-w-3xl p-8">
      <button
        type="button"
        onClick={() => navigate(`/workspaces/${workspaceId}`)}
        className="mb-4 inline-flex items-center gap-1 text-xs text-ink-tertiary hover:text-ink-secondary"
      >
        <ArrowLeft className="size-3" /> Back
      </button>
      <PageHeader
        title="Pending sync changes"
        description="Edits on tables where a push to the source requires approval first."
      />

      <YourDrafts workspaceId={workspaceId} />

      {/* isError here just means "not an owner/admin" (403) -- reviewing
          submitted batches is admin-only, so this section renders nothing
          rather than an error for anyone else. */}
      {!isError && (
        <>
          {isLoading && <ListRowsSkeleton count={4} />}

          {!isLoading && batches?.length === 0 ? (
            <EmptyState icon={ShieldCheck} title="Nothing waiting" description="Every submitted batch is fully caught up." />
          ) : (
            <div key={isLoading ? "loading" : "loaded"} className="animate-fade-in space-y-3">
              {batches?.map((batch) => (
                <Card key={batch.id}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-ink-primary">
                        {batch.changes.length} change{batch.changes.length === 1 ? "" : "s"} from {batch.requested_by_name}
                      </p>
                      <p className="mt-0.5 text-xs text-ink-tertiary">{new Date(batch.submitted_at).toLocaleString()}</p>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button variant="ghost" size="sm" onClick={() => setRejecting(batch)}>
                        <X className="size-3.5" /> Reject
                      </Button>
                      <Button variant="secondary" size="sm" loading={approve.isPending} onClick={() => approve.mutate(batch.id)}>
                        <Check className="size-3.5" /> Approve all
                      </Button>
                    </div>
                  </div>
                  <div className="mt-2 divide-y divide-border">
                    {batch.changes.map((change) => (
                      <ChangeRow key={change.id} change={change} />
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}

      <RejectDialog batch={rejecting} onClose={() => setRejecting(null)} />
    </div>
  );
}
