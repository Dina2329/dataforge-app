import { useState } from "react";
import {
  useBatchSubmitJobs,
  useBatchSubmitPreview,
  useCreateBatchSubmitJob,
  useDismissBatchSubmitJob,
} from "../../hooks/useBatchSubmit";
import { apiErrorMessage } from "../../lib/apiClient";
import type { BatchSubmitJobStatus } from "../../types";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";

const STATUS_LABEL: Record<BatchSubmitJobStatus, string> = {
  queued: "Queued",
  running: "Sending…",
  completed: "Completed",
  partially_failed: "Partially failed",
  failed: "Failed",
};

const STATUS_CLASS: Record<BatchSubmitJobStatus, string> = {
  queued: "text-ink-tertiary",
  running: "text-accent-secondary",
  completed: "text-status-success",
  partially_failed: "text-status-warning",
  failed: "text-status-danger",
};

interface BatchSubmitDialogProps {
  tableId: string;
  open: boolean;
  onClose: () => void;
}

/** "Send batch to API" -- shows how many rows are currently marked (the
 * table's configured boolean "ready to send" field) and in how many
 * batches that'll go out, a Send button (blocked server-side to one
 * active job per table at a time), the active/most-recent job's live
 * progress, and a short history of past sends with per-batch results so a
 * partial failure's rows are identifiable for a manual retry (marked rows
 * are never auto-cleared -- see BatchSubmitConfigDialog's own docstring). */
export function BatchSubmitDialog({ tableId, open, onClose }: BatchSubmitDialogProps) {
  const { data: preview, isLoading: previewLoading, error: previewError } = useBatchSubmitPreview(tableId, open);
  const { data: jobs } = useBatchSubmitJobs(tableId);
  const createJob = useCreateBatchSubmitJob(tableId);
  const dismissJob = useDismissBatchSubmitJob(tableId);
  const [error, setError] = useState<string | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);

  const activeJob = (jobs ?? []).find((j) => j.status === "queued" || j.status === "running");
  const history = (jobs ?? []).filter((j) => j.id !== activeJob?.id);

  async function handleSend() {
    setError(null);
    try {
      await createJob.mutateAsync();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not start the batch send"));
    }
  }

  function handleClose() {
    setError(null);
    onClose();
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Send batch to API" size="lg">
      {previewLoading ? (
        <p className="mb-4 text-sm text-ink-tertiary">Checking marked rows…</p>
      ) : previewError ? (
        <p className="mb-4 text-sm text-status-danger">{apiErrorMessage(previewError, "Batch Submit isn't configured for this table yet")}</p>
      ) : preview ? (
        <p className="mb-4 text-sm text-ink-secondary">
          <span className="font-medium text-ink-primary">{preview.matched_count}</span> row{preview.matched_count === 1 ? "" : "s"} marked
          ready to send, as <span className="font-medium text-ink-primary">{preview.total_batches}</span> batch
          {preview.total_batches === 1 ? "" : "es"} of up to {preview.batch_size} each.
        </p>
      ) : null}

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}

      <Button
        onClick={handleSend}
        loading={createJob.isPending}
        disabled={!preview || preview.matched_count === 0 || !!activeJob}
        className="mb-4 w-full"
      >
        {activeJob ? "A send is already in progress…" : "Send batch to API"}
      </Button>

      {activeJob && (
        <div className="mb-4 rounded-lg border border-border-default p-3 text-xs">
          <div className="mb-1 flex items-center justify-between">
            <span className="font-medium text-ink-primary">Current send</span>
            <span className={STATUS_CLASS[activeJob.status]}>{STATUS_LABEL[activeJob.status]}</span>
          </div>
          <p className="text-ink-tertiary">
            {activeJob.sent_batches + activeJob.failed_batches} of {activeJob.total_batches ?? "?"} batch(es) processed
            {activeJob.failed_batches > 0 && <span className="text-status-warning"> · {activeJob.failed_batches} failed so far</span>}
          </p>
        </div>
      )}

      {history.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium text-ink-secondary">History</p>
          <div className="max-h-72 space-y-1.5 overflow-y-auto">
            {history.map((job) => {
              const isExpanded = expandedJobId === job.id;
              const failedResults = job.batch_results.filter((b) => b.status === "failed");
              return (
                <div key={job.id} className="rounded-lg border border-border-default p-2.5 text-xs">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className={STATUS_CLASS[job.status]}>{STATUS_LABEL[job.status]}</span>
                    <span className="text-ink-tertiary">{new Date(job.created_at).toLocaleString()}</span>
                  </div>
                  <div className="mb-2 text-ink-tertiary">
                    {job.sent_batches} sent · {job.failed_batches} failed · {job.total_rows ?? 0} row(s) marked at the time
                  </div>
                  <div className="flex gap-1.5">
                    {failedResults.length > 0 && (
                      <Button size="sm" variant="secondary" onClick={() => setExpandedJobId(isExpanded ? null : job.id)}>
                        {isExpanded ? "Hide" : "View"} failed batches
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" loading={dismissJob.isPending} onClick={() => dismissJob.mutate(job.id)}>
                      Dismiss
                    </Button>
                  </div>
                  {isExpanded && (
                    <div className="mt-2 space-y-1 border-t border-border-default pt-2">
                      {failedResults.map((b) => (
                        <div key={b.batch_index} className="text-status-danger">
                          Batch {b.batch_index + 1} ({b.row_ids.length} row{b.row_ids.length === 1 ? "" : "s"}): {b.error}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Dialog>
  );
}
