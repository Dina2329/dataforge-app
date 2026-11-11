import { ArrowLeft, Database, History, LayoutDashboard, Plug, ShieldAlert, SlidersHorizontal, Table2, Users, Zap } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useAuditLog } from "../hooks/useAuditLog";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import { apiErrorMessage } from "../lib/apiClient";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import { PageHeader } from "../components/shared/PageHeader";
import { EmptyState } from "../components/shared/EmptyState";
import { ListRowsSkeleton } from "../components/ui/Skeleton";
import type { ComponentType } from "react";

const RESOURCE_TYPES = ["record", "field", "table", "base", "automation", "bulk_op", "data_source", "dashboard", "member"] as const;

const RESOURCE_ICONS: Record<string, ComponentType<{ className?: string }>> = {
  record: Table2,
  field: Table2,
  table: Table2,
  base: Database,
  automation: Zap,
  bulk_op: SlidersHorizontal,
  data_source: Plug,
  dashboard: LayoutDashboard,
  member: Users,
};

function actionLabel(action: string): string {
  return action.replace(/[._]/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export function AuditLogPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  useReportWorkspaceContext(workspaceId);
  const [searchParams, setSearchParams] = useSearchParams();
  const resourceType = searchParams.get("resource_type") ?? "";

  const { data: entries, isLoading, isError, error } = useAuditLog(workspaceId, resourceType || undefined);

  if (isError) {
    return (
      <div className="mx-auto max-w-3xl p-8">
        <EmptyState
          icon={ShieldAlert}
          title="Can't view the audit log"
          description={apiErrorMessage(error, "You don't have permission to view this workspace's audit log.")}
        />
      </div>
    );
  }

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
        title="Audit log"
        description="Who did what, and when — visible to owners and admins only."
        actions={
          <Select
            value={resourceType}
            onChange={(e) => setSearchParams(e.target.value ? { resource_type: e.target.value } : {})}
            className="w-40"
          >
            <option value="">All activity</option>
            {RESOURCE_TYPES.map((rt) => (
              <option key={rt} value={rt}>
                {actionLabel(rt)}
              </option>
            ))}
          </Select>
        }
      />

      {isLoading && <ListRowsSkeleton count={6} />}

      {entries?.length === 0 ? (
        <EmptyState icon={History} title="No activity yet" description="Actions taken in this workspace will show up here." />
      ) : (
        <div key={isLoading ? "loading" : "loaded"} className="animate-fade-in space-y-2">
          {entries?.map((entry) => {
            const Icon = RESOURCE_ICONS[entry.resource_type] ?? History;
            return (
              <Card key={entry.id} className="flex items-center gap-3">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-secondary-tint">
                  <Icon className="size-4 text-accent-secondary" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-medium text-ink-primary">{actionLabel(entry.action)}</p>
                    {entry.resource_label && <Badge tone="neutral" dot={false}>{entry.resource_label}</Badge>}
                  </div>
                  <p className="mt-0.5 truncate text-xs text-ink-tertiary">
                    {entry.actor_email ?? "System"} · {new Date(entry.created_at).toLocaleString()}
                  </p>
                  {Array.isArray(entry.details?.changed_fields) && entry.details.changed_fields.length > 0 && (
                    <p className="mt-0.5 truncate text-xs text-ink-tertiary">
                      Changed: {(entry.details.changed_fields as string[]).join(", ")}
                    </p>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
