import { useState } from "react";
import { LayoutDashboard, Plus, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useCreateDashboard, useDashboards, useDeleteDashboard } from "../hooks/useDashboards";
import { useWorkspaces } from "../hooks/useWorkspaces";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import { Button } from "../components/ui/Button";
import { CardLink } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { FormField } from "../components/ui/FormField";
import { Input } from "../components/ui/Input";
import { PageHeader } from "../components/shared/PageHeader";
import { EmptyState } from "../components/shared/EmptyState";
import { CardGridSkeleton } from "../components/ui/Skeleton";
import { ConfirmDeleteDialog } from "../components/shared/ConfirmDeleteDialog";
import type { Dashboard } from "../types";

export function DashboardsListPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  useReportWorkspaceContext(workspaceId);
  const navigate = useNavigate();
  const { data: workspaces } = useWorkspaces();
  const workspaceName = workspaces?.find((w) => w.id === workspaceId)?.name;
  const { data: dashboards, isLoading } = useDashboards(workspaceId);
  const createDashboard = useCreateDashboard(workspaceId);
  const deleteDashboard = useDeleteDashboard(workspaceId);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Dashboard | null>(null);

  async function handleCreate() {
    if (!name.trim()) return;
    const dashboard = await createDashboard.mutateAsync(name.trim());
    setName("");
    setOpen(false);
    navigate(`/dashboards/${dashboard.id}`);
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    await deleteDashboard.mutateAsync(deleteTarget.id);
    setDeleteTarget(null);
  }

  return (
    <div className="mx-auto max-w-4xl p-8">
      <PageHeader
        title="Dashboards"
        description="Visualize your data with charts and KPI tiles"
        breadcrumbs={workspaceName ? [{ label: workspaceName, to: "/" }, { label: "Dashboards" }] : undefined}
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus className="size-4" /> New dashboard
          </Button>
        }
      />

      {isLoading && <CardGridSkeleton />}

      {dashboards?.length === 0 ? (
        <EmptyState
          icon={LayoutDashboard}
          title="No dashboards yet"
          description="Create one to visualize your data."
          action={
            <Button onClick={() => setOpen(true)}>
              <Plus className="size-4" /> New dashboard
            </Button>
          }
        />
      ) : (
        <div key={isLoading ? "loading" : "loaded"} className="animate-fade-in grid grid-cols-1 gap-2.5 sm:grid-cols-2 md:grid-cols-3">
          {dashboards?.map((dashboard) => (
            <Link key={dashboard.id} to={`/dashboards/${dashboard.id}`}>
              <CardLink className="group flex items-center gap-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-accent-secondary-tint">
                  <LayoutDashboard className="size-4 text-accent-secondary" strokeWidth={1.75} />
                </div>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink-primary">{dashboard.name}</span>
                <button
                  type="button"
                  aria-label="Delete dashboard"
                  className="shrink-0 rounded p-1 text-ink-tertiary opacity-0 transition-opacity hover:bg-status-danger-tint hover:text-status-danger group-hover:opacity-100 focus-visible:opacity-100"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setDeleteTarget(dashboard);
                  }}
                >
                  <Trash2 className="size-3.5" />
                </button>
              </CardLink>
            </Link>
          ))}
        </div>
      )}

      <Dialog open={open} onClose={() => setOpen(false)} title="New dashboard">
        <FormField label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sales Overview" autoFocus />
        </FormField>
        <Button onClick={handleCreate} loading={createDashboard.isPending} className="mt-4 w-full">
          Create dashboard
        </Button>
      </Dialog>

      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        loading={deleteDashboard.isPending}
        title="Delete dashboard"
        description={`This permanently deletes "${deleteTarget?.name}" and all of its widgets. This can't be undone.`}
      />
    </div>
  );
}
