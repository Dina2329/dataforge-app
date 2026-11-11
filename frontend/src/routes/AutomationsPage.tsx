import { useState } from "react";
import { ArrowLeft, CheckCircle2, ChevronDown, ChevronRight, Clock, Plus, Trash2, XCircle, Zap } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { useTable } from "../hooks/useBases";
import { useBase } from "../hooks/useDataSources";
import {
  useAutomationActions,
  useAutomationRuns,
  useAutomations,
  useDeleteAutomation,
  useDeleteAutomationAction,
  useUpdateAutomation,
} from "../hooks/useAutomations";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import { CreateAutomationDialog } from "../components/automations/CreateAutomationDialog";
import { ACTION_LABELS, AddActionDialog } from "../components/automations/AddActionDialog";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/shared/EmptyState";
import { PageHeader } from "../components/shared/PageHeader";
import { ListRowsSkeleton } from "../components/ui/Skeleton";
import type { Automation, AutomationAction, Field, TriggerType } from "../types";

const TRIGGER_LABELS: Record<TriggerType, string> = {
  record_created: "On create",
  record_updated: "On update",
  scheduled: "Scheduled",
};

export function AutomationsPage() {
  const { tableId } = useParams<{ tableId: string }>();
  const navigate = useNavigate();
  const { data: table } = useTable(tableId);
  const { data: base } = useBase(table?.base_id);
  useReportWorkspaceContext(base?.workspace_id);

  const { data: automations, isLoading } = useAutomations(tableId);
  const updateAutomation = useUpdateAutomation(tableId);
  const deleteAutomation = useDeleteAutomation(tableId);

  const [createOpen, setCreateOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="mx-auto max-w-3xl p-8">
      <button
        type="button"
        onClick={() => navigate(`/tables/${tableId}`)}
        className="mb-4 inline-flex items-center gap-1 text-xs text-ink-tertiary hover:text-ink-secondary"
      >
        <ArrowLeft className="size-3" /> Back to {table?.name ?? "table"}
      </button>
      <PageHeader
        title="Automations"
        description="Run actions automatically when records change, or on a schedule"
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" /> New automation
          </Button>
        }
      />

      {isLoading && <ListRowsSkeleton count={3} />}

      {automations?.length === 0 ? (
        <EmptyState icon={Zap} title="No automations yet" description="Create one to react to record changes or run on a schedule." />
      ) : (
        <div key={isLoading ? "loading" : "loaded"} className="animate-fade-in space-y-2">
          {automations?.map((automation) => (
            <AutomationRow
              key={automation.id}
              automation={automation}
              baseId={table?.base_id}
              sourceFields={table?.fields ?? []}
              expanded={expandedId === automation.id}
              onToggleExpand={() => setExpandedId(expandedId === automation.id ? null : automation.id)}
              onToggleEnabled={() => updateAutomation.mutate({ id: automation.id, is_enabled: !automation.is_enabled })}
              onDelete={() => deleteAutomation.mutate(automation.id)}
            />
          ))}
        </div>
      )}

      {tableId && (
        <CreateAutomationDialog
          tableId={tableId}
          fields={table?.fields ?? []}
          open={createOpen}
          onClose={() => setCreateOpen(false)}
        />
      )}
    </div>
  );
}

interface AutomationRowProps {
  automation: Automation;
  baseId: string | undefined;
  sourceFields: Field[];
  expanded: boolean;
  onToggleExpand: () => void;
  onToggleEnabled: () => void;
  onDelete: () => void;
}

function describeAction(action: AutomationAction): string {
  const values = (action.config as { values?: Record<string, unknown> }).values;
  if (!values || Object.keys(values).length === 0) return ACTION_LABELS[action.action_type];
  const summary = Object.entries(values)
    .map(([field, value]) => `${field} = ${value}`)
    .join(", ");
  return `${ACTION_LABELS[action.action_type]}: ${summary}`;
}

function AutomationRow({ automation, baseId, sourceFields, expanded, onToggleExpand, onToggleEnabled, onDelete }: AutomationRowProps) {
  const { data: actions } = useAutomationActions(expanded ? automation.id : undefined);
  const { data: runs } = useAutomationRuns(expanded ? automation.id : undefined);
  const deleteAction = useDeleteAutomationAction(automation.id);
  const [addActionOpen, setAddActionOpen] = useState(false);

  return (
    <Card className="p-0">
      <div className="flex w-full items-center justify-between gap-3 p-4">
        <button type="button" onClick={onToggleExpand} className="flex flex-1 items-center gap-3 text-left">
          {expanded ? <ChevronDown className="size-4 text-ink-tertiary" /> : <ChevronRight className="size-4 text-ink-tertiary" />}
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-secondary-tint">
            <Zap className="size-4 text-accent-secondary" />
          </div>
          <div>
            <p className="text-sm font-medium text-ink-primary">{automation.name}</p>
            <div className="mt-0.5 flex items-center gap-1.5">
              <Badge tone="info" dot={false}>{TRIGGER_LABELS[automation.trigger_type]}</Badge>
              {automation.trigger_type === "scheduled" && automation.trigger_config.cron && (
                <span className="text-xs text-ink-tertiary">{automation.trigger_config.cron}</span>
              )}
              {automation.trigger_config.watched_fields && automation.trigger_config.watched_fields.length > 0 && (
                <span className="text-xs text-ink-tertiary">on {automation.trigger_config.watched_fields.join(", ")}</span>
              )}
            </div>
          </div>
        </button>
        <div className="flex items-center gap-2">
          <Button variant={automation.is_enabled ? "secondary" : "outline"} size="sm" onClick={onToggleEnabled}>
            {automation.is_enabled ? "Enabled" : "Disabled"}
          </Button>
          <Button variant="danger" size="sm" onClick={onDelete} aria-label="Delete automation">
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border-default p-4">
          <div className="mb-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-semibold text-ink-secondary">Actions</p>
              <Button variant="secondary" size="sm" onClick={() => setAddActionOpen(true)}>
                <Plus className="size-3.5" /> Add action
              </Button>
            </div>
            {actions?.length ? (
              <div className="space-y-1.5">
                {actions.map((action) => (
                  <div
                    key={action.id}
                    className="flex items-center justify-between gap-2 rounded-lg bg-surface-raised px-3 py-2 text-xs"
                  >
                    <span className="min-w-0 truncate font-medium text-ink-secondary" title={describeAction(action)}>
                      {describeAction(action)}
                    </span>
                    <button
                      type="button"
                      onClick={() => deleteAction.mutate(action.id)}
                      className="shrink-0 text-ink-tertiary hover:text-status-danger"
                      aria-label="Delete action"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-ink-tertiary">No actions yet — this automation won't do anything until you add one.</p>
            )}
          </div>

          <div>
            <p className="mb-2 text-xs font-semibold text-ink-secondary">Recent runs</p>
            {runs?.length ? (
              <div className="space-y-1.5">
                {runs.map((run) => (
                  <div key={run.id} className="flex items-center gap-2 rounded-lg bg-surface-raised px-3 py-2 text-xs">
                    {run.status === "success" ? (
                      <CheckCircle2 className="size-3.5 shrink-0 text-status-success" />
                    ) : (
                      <XCircle className="size-3.5 shrink-0 text-status-danger" />
                    )}
                    <span className="flex items-center gap-1 text-ink-tertiary">
                      <Clock className="size-3 shrink-0" />
                      {new Date(run.ran_at).toLocaleString()}
                    </span>
                    {run.error && <span className="truncate text-status-danger">{run.error}</span>}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-ink-tertiary">No runs yet.</p>
            )}
          </div>

          <AddActionDialog
            automationId={automation.id}
            baseId={baseId}
            sourceFields={sourceFields}
            triggerType={automation.trigger_type}
            open={addActionOpen}
            onClose={() => setAddActionOpen(false)}
          />
        </div>
      )}
    </Card>
  );
}
