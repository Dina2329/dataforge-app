import { useState } from "react";
import { AlertTriangle, ArrowDownToLine, Check, ClipboardList, Play, RefreshCw, ShieldCheck, Unlink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { Field } from "../../types";
import {
  useRunTableSyncPullNow,
  useSetPushRequiresApproval,
  useSetTableSyncEnabled,
  useTableSync,
  useUnlinkTableSync,
} from "../../hooks/useDataSources";
import { DropdownItem, DropdownMenu } from "../ui/DropdownMenu";
import { ConfirmDeleteDialog } from "../shared/ConfirmDeleteDialog";
import { ConfigurePullDialog } from "./ConfigurePullDialog";

function minutesLabel(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `${minutes}m` : `${Math.round(minutes / 60)}h`;
}

// Renders nothing for the overwhelming majority of tables (no sync_enabled
// config at all) -- only ever visible on a table imported with "keep in
// sync" checked (see ImportFromSourceDialog).
export function TableSyncStatus({ tableId, fields, workspaceId }: { tableId: string; fields: Field[]; workspaceId?: string }) {
  const navigate = useNavigate();
  const { data: config } = useTableSync(tableId);
  const setEnabled = useSetTableSyncEnabled(tableId);
  const setRequiresApproval = useSetPushRequiresApproval(tableId);
  const unlink = useUnlinkTableSync(tableId);
  const runPullNow = useRunTableSyncPullNow(tableId);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [configurePullOpen, setConfigurePullOpen] = useState(false);

  if (!config) return null;

  const healthy = config.sync_enabled && config.consecutive_failures === 0;
  const pullEnabled = config.external_updated_at_column !== null;
  const pullHealthy = pullEnabled && !config.poll_paused && config.poll_consecutive_failures === 0;

  return (
    <>
      <div className="flex items-center gap-1.5">
        <DropdownMenu
          align="left"
          trigger={
            <span
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-xs font-medium ${
                healthy
                  ? "bg-status-success-tint text-status-success"
                  : config.sync_enabled
                    ? "bg-status-warning-tint text-status-warning"
                    : "bg-surface-raised text-ink-tertiary"
              }`}
            >
              <RefreshCw className="size-3.5" />
              {config.sync_enabled ? (config.consecutive_failures > 0 ? "Sync failing" : "Synced") : "Sync paused"}
              {config.push_requires_approval && (
                <span title="Push requires approval">
                  <ShieldCheck className="size-3.5" aria-label="Push requires approval" />
                </span>
              )}
            </span>
          }
        >
          <div className="max-w-72 px-2.5 py-1.5 text-xs text-ink-tertiary">
            Synced with <span className="font-medium text-ink-secondary">{config.external_table_name}</span>
            {config.last_error && (
              <p className="mt-1 flex items-start gap-1 text-status-danger">
                <AlertTriangle className="mt-0.5 size-3 shrink-0" /> {config.last_error}
              </p>
            )}
          </div>
          <DropdownItem onClick={() => setEnabled.mutate(!config.sync_enabled)}>
            {config.sync_enabled ? "Pause sync" : "Resume sync"}
          </DropdownItem>
          <DropdownItem
            onClick={() => setRequiresApproval.mutate({ syncEnabled: config.sync_enabled, requiresApproval: !config.push_requires_approval })}
          >
            <ShieldCheck className="size-3.5" />
            Require approval before pushing
            {config.push_requires_approval && <Check className="ml-auto size-3.5 text-accent" />}
          </DropdownItem>
          {config.push_requires_approval && workspaceId && (
            <DropdownItem onClick={() => navigate(`/workspaces/${workspaceId}/pending-sync-changes`)}>
              <ClipboardList className="size-3.5" /> View pending changes
            </DropdownItem>
          )}
          <DropdownItem onClick={() => setConfigurePullOpen(true)}>
            <ArrowDownToLine className="size-3.5" /> {pullEnabled ? "Configure pull" : "Pull changes from source…"}
          </DropdownItem>
          <DropdownItem onClick={() => setConfirmUnlink(true)} className="text-status-danger hover:text-status-danger">
            <Unlink className="size-3.5" /> Unlink
          </DropdownItem>
        </DropdownMenu>

        {pullEnabled && (
          <DropdownMenu
            align="left"
            trigger={
              <span
                className={`flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-xs font-medium ${
                  pullHealthy
                    ? "bg-status-success-tint text-status-success"
                    : !config.poll_paused
                      ? "bg-status-warning-tint text-status-warning"
                      : "bg-surface-raised text-ink-tertiary"
                }`}
              >
                <ArrowDownToLine className="size-3.5" />
                {config.poll_paused ? "Pull paused" : config.poll_consecutive_failures > 0 ? "Pull failing" : "Pulling"}
                {!config.poll_paused && config.poll_interval_seconds && ` · every ${minutesLabel(config.poll_interval_seconds)}`}
              </span>
            }
          >
            <div className="max-w-72 px-2.5 py-1.5 text-xs text-ink-tertiary">
              Checking <span className="font-medium text-ink-secondary">{config.external_updated_at_column}</span> for changes
              {config.poll_last_error && (
                <p className="mt-1 flex items-start gap-1 text-status-danger">
                  <AlertTriangle className="mt-0.5 size-3 shrink-0" /> {config.poll_last_error}
                </p>
              )}
            </div>
            <DropdownItem onClick={() => runPullNow.mutate()} disabled={runPullNow.isPending}>
              <Play className="size-3.5" /> {config.poll_paused ? "Resume & sync now" : "Sync now"}
            </DropdownItem>
            <DropdownItem onClick={() => setConfigurePullOpen(true)}>Configure pull</DropdownItem>
          </DropdownMenu>
        )}
      </div>

      <ConfigurePullDialog
        tableId={tableId}
        fields={fields}
        currentColumn={config.external_updated_at_column}
        currentPollIntervalSeconds={config.poll_interval_seconds}
        currentDeletionIntervalSeconds={config.deletion_check_interval_seconds}
        open={configurePullOpen}
        onClose={() => setConfigurePullOpen(false)}
      />
      <ConfirmDeleteDialog
        open={confirmUnlink}
        onClose={() => setConfirmUnlink(false)}
        onConfirm={() => {
          unlink.mutate();
          setConfirmUnlink(false);
        }}
        loading={unlink.isPending}
        title="Unlink sync"
        description={`This table stops syncing with "${config.external_table_name}". Existing data stays — future edits here will no longer be pushed anywhere.`}
      />
    </>
  );
}
