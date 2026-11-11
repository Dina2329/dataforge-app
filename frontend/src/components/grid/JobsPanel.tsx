import { ListChecks } from "lucide-react";
import { useDismissMissingTermsJob, useMissingTermsJobs, useRetryMissingTermsJob } from "../../hooks/useMissingTerms";
import type { MissingTermsJob, MissingTermsJobStatus } from "../../types";
import { Button } from "../ui/Button";
import { DropdownMenu } from "../ui/DropdownMenu";

const STATUS_LABEL: Record<MissingTermsJobStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  partially_failed: "Partially failed",
  failed: "Failed",
};

const STATUS_CLASS: Record<MissingTermsJobStatus, string> = {
  queued: "text-ink-tertiary",
  running: "text-accent-secondary",
  completed: "text-status-success",
  partially_failed: "text-status-warning",
  failed: "text-status-danger",
};

interface JobsPanelProps {
  tableId: string;
  onViewResults: (jobId: string) => void;
}

/** Small toggle + badge in the toolbar, opening a dropdown listing this
 * user's own Missing Terms jobs for this table -- polls every few seconds
 * only while something is queued/running (see useMissingTermsJobs), stops
 * otherwise. Jobs are stored server-side, so this survives refresh/navigation;
 * a toast on completion comes from the existing notification bell, this is
 * the richer per-job management surface. */
export function JobsPanel({ tableId, onViewResults }: JobsPanelProps) {
  const { data: jobs } = useMissingTermsJobs(tableId);
  const retryJob = useRetryMissingTermsJob(tableId);
  const dismissJob = useDismissMissingTermsJob(tableId);

  const activeCount = (jobs ?? []).filter((j) => j.status === "queued" || j.status === "running").length;

  function formatRow(job: MissingTermsJob) {
    const rows = job.submitted_rows as { sub_domain: string; term_name: string }[];
    const first = rows[0];
    const label = first ? `${first.sub_domain} — ${first.term_name}` : "(no rows)";
    const extra = rows.length - 1;

    return (
      <div key={job.id} className="rounded-lg border border-border-default p-2.5 text-xs">
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="truncate font-medium text-ink-primary" title={label}>
            {label}
            {extra > 0 && <span className="font-normal text-ink-tertiary"> +{extra} more</span>}
          </span>
          <span className={STATUS_CLASS[job.status]}>{STATUS_LABEL[job.status]}</span>
        </div>
        <div className="mb-2 text-ink-tertiary">
          {job.submitted_rows.length} row{job.submitted_rows.length === 1 ? "" : "s"} · {new Date(job.created_at).toLocaleString()}
        </div>
        <div className="flex gap-1.5">
          {(job.status === "completed" || job.status === "partially_failed") && (
            <Button size="sm" variant="secondary" onClick={() => onViewResults(job.id)}>
              View results
            </Button>
          )}
          {(job.status === "failed" || job.status === "partially_failed") && (
            <Button size="sm" variant="secondary" loading={retryJob.isPending} onClick={() => retryJob.mutate(job.id)}>
              Retry
            </Button>
          )}
          {job.status !== "queued" && job.status !== "running" && (
            <Button size="sm" variant="ghost" loading={dismissJob.isPending} onClick={() => dismissJob.mutate(job.id)}>
              Dismiss
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <DropdownMenu
      trigger={
        <span className="relative inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-ink-primary ring-1 ring-inset ring-border-strong">
          <ListChecks className="size-4" /> Jobs
          {activeCount > 0 && (
            <span className="absolute -right-1.5 -top-1.5 flex size-4 items-center justify-center rounded-full bg-accent text-[10px] text-white">
              {activeCount}
            </span>
          )}
        </span>
      }
    >
      <div className="max-h-96 w-80 space-y-1.5 overflow-y-auto p-1">
        {(jobs ?? []).length === 0 && <p className="p-2 text-center text-xs text-ink-tertiary">No jobs yet.</p>}
        {(jobs ?? []).map(formatRow)}
      </div>
    </DropdownMenu>
  );
}
