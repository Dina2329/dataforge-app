import { useState } from "react";
import { Camera, Clock, History, RotateCcw, Trash2 } from "lucide-react";
import { useBase } from "../../hooks/useDataSources";
import {
  useCreateSnapshot,
  useDeleteSnapshot,
  usePreviewRestore,
  useRestoreSnapshot,
  useSetAutoSnapshotsEnabled,
  useSnapshots,
} from "../../hooks/useSnapshots";
import type { BaseSnapshot, RestoreSnapshotResult, SnapshotTableRestoreResult } from "../../types";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { Switch } from "../ui/Switch";
import { EmptyState } from "../shared/EmptyState";
import { ConfirmDeleteDialog } from "../shared/ConfirmDeleteDialog";
import { ListRowsSkeleton } from "../ui/Skeleton";

function TableChangeSummary({ t }: { t: SnapshotTableRestoreResult }) {
  return (
    <div className="rounded-lg border border-border-default p-3 text-sm">
      <p className="font-medium text-ink-primary">{t.table_name}</p>
      {t.skipped ? (
        <p className="mt-0.5 text-xs text-ink-tertiary">{t.skip_reason}</p>
      ) : (
        <p className="mt-0.5 text-xs text-ink-tertiary">
          {t.updated} updated · {t.created} recreated · {t.deleted} removed · {t.unchanged} unchanged
          {t.failed > 0 && <span className="text-status-danger"> · {t.failed} failed</span>}
        </p>
      )}
    </div>
  );
}

function RestoreResultSummary({ result, onClose }: { result: RestoreSnapshotResult; onClose: () => void }) {
  return (
    <Dialog open title="Restore complete" onClose={onClose}>
      <div className="space-y-2">
        {result.tables.map((t) => (
          <TableChangeSummary key={t.table_name} t={t} />
        ))}
      </div>
      <Button onClick={onClose} className="mt-4 w-full">
        Done
      </Button>
    </Dialog>
  );
}

function RestoreConfirmDialog({
  snapshot,
  onClose,
  onConfirm,
  loading,
}: {
  snapshot: BaseSnapshot | null;
  onClose: () => void;
  onConfirm: () => void;
  loading: boolean;
}) {
  const { data: preview, isLoading } = usePreviewRestore(snapshot?.id);
  if (!snapshot) return null;
  const hasChanges = preview?.tables.some((t) => !t.skipped && (t.created > 0 || t.updated > 0 || t.deleted > 0));

  return (
    <Dialog open title="Restore this snapshot?" onClose={onClose}>
      <p className="mb-3 text-sm text-ink-secondary">
        This brings every table in this base back to how it looked at "{snapshot.label}". Edits made since are reverted (as ordinary
        edits, so sync and approval rules still apply) -- this doesn't touch tables created after this snapshot was taken.
      </p>

      {isLoading && <ListRowsSkeleton count={2} />}

      {preview && (
        <div className="mb-4 space-y-2">
          {preview.tables.map((t) => (
            <TableChangeSummary key={t.table_name} t={t} />
          ))}
          {!hasChanges && (
            <p className="text-xs text-ink-tertiary">Nothing has changed since this snapshot -- restoring would be a no-op.</p>
          )}
        </div>
      )}

      <div className="flex gap-2">
        <Button variant="secondary" onClick={onClose} className="flex-1">
          Cancel
        </Button>
        <Button variant="danger" onClick={onConfirm} loading={loading} className="flex-1">
          Restore
        </Button>
      </div>
    </Dialog>
  );
}

export function SnapshotsDialog({ baseId, open, onClose }: { baseId: string; open: boolean; onClose: () => void }) {
  const { data: base } = useBase(baseId);
  const { data: snapshots, isLoading } = useSnapshots(baseId);
  const createSnapshot = useCreateSnapshot(baseId);
  const deleteSnapshot = useDeleteSnapshot(baseId);
  const restoreSnapshot = useRestoreSnapshot(baseId);
  const setAutoSnapshotsEnabled = useSetAutoSnapshotsEnabled(baseId);

  const [label, setLabel] = useState("");
  const [restoreTarget, setRestoreTarget] = useState<BaseSnapshot | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<BaseSnapshot | null>(null);
  const [restoreResult, setRestoreResult] = useState<RestoreSnapshotResult | null>(null);

  return (
    <>
      <Dialog open={open} onClose={onClose} title="Snapshots" size="lg">
        <p className="mb-4 text-sm text-ink-secondary">
          A snapshot remembers every table in this base, data and schema, at one moment. Restoring brings the base back to that moment
          -- edits made since are replayed as an undo, not a raw overwrite, so they still follow this base's own rules (sync, approval
          gates, and so on).
        </p>

        <div className="mb-4 flex items-center justify-between rounded-lg border border-border-default p-3">
          <div>
            <p className="text-sm font-medium text-ink-primary">Automatic daily snapshots</p>
            <p className="text-xs text-ink-tertiary">
              A snapshot taken every night, kept for 7 days. Manual snapshots below are never affected by this.
            </p>
          </div>
          {base && (
            <Switch
              checked={base.auto_snapshots_enabled}
              onChange={(checked) => setAutoSnapshotsEnabled.mutate(checked)}
              disabled={setAutoSnapshotsEnabled.isPending}
              aria-label="Automatic daily snapshots"
            />
          )}
        </div>

        <div className="mb-4 flex gap-2">
          <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label (optional)" className="flex-1" />
          <Button
            loading={createSnapshot.isPending}
            onClick={() => {
              createSnapshot.mutate(label.trim() || null);
              setLabel("");
            }}
          >
            <Camera className="size-4" /> Take snapshot
          </Button>
        </div>

        {isLoading && <ListRowsSkeleton count={3} />}

        {snapshots?.length === 0 ? (
          <EmptyState icon={History} title="No snapshots yet" description="Take one before a risky change, or wait for tomorrow's automatic one." />
        ) : (
          <div className="space-y-2">
            {snapshots?.map((s) => (
              <div key={s.id} className="flex items-center gap-3 rounded-lg border border-border-default p-3">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-secondary-tint">
                  <Clock className="size-4 text-accent-secondary" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-medium text-ink-primary">{s.label}</p>
                    {s.is_automatic && <Badge tone="neutral">automatic</Badge>}
                  </div>
                  <p className="text-xs text-ink-tertiary">
                    {new Date(s.created_at).toLocaleString()} · {s.table_count} table{s.table_count === 1 ? "" : "s"}
                  </p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setRestoreTarget(s)}>
                  <RotateCcw className="size-3.5" /> Restore
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setDeleteTarget(s)}
                  className="text-status-danger hover:text-status-danger"
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </Dialog>

      <RestoreConfirmDialog
        snapshot={restoreTarget}
        loading={restoreSnapshot.isPending}
        onClose={() => setRestoreTarget(null)}
        onConfirm={() => {
          if (!restoreTarget) return;
          restoreSnapshot.mutate(restoreTarget.id, { onSuccess: (result) => setRestoreResult(result) });
          setRestoreTarget(null);
        }}
      />

      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        loading={deleteSnapshot.isPending}
        title="Delete snapshot"
        description={`"${deleteTarget?.label}" will be gone for good -- you won't be able to restore to this point afterward.`}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteSnapshot.mutate(deleteTarget.id);
          setDeleteTarget(null);
        }}
      />

      {restoreResult && <RestoreResultSummary result={restoreResult} onClose={() => setRestoreResult(null)} />}
    </>
  );
}
