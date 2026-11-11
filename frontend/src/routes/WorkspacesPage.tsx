import { useState } from "react";
import { Link } from "react-router-dom";
import { Building2, Plus, Trash2 } from "lucide-react";
import { useCreateWorkspace, useDeleteWorkspace, useWorkspaces } from "../hooks/useWorkspaces";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import { Button } from "../components/ui/Button";
import { CardLink } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { Input } from "../components/ui/Input";
import { PageHeader } from "../components/shared/PageHeader";
import { EmptyState } from "../components/shared/EmptyState";
import { CardGridSkeleton } from "../components/ui/Skeleton";
import type { Workspace } from "../types";

export function WorkspacesPage() {
  useReportWorkspaceContext(null);
  const { data: workspaces, isLoading } = useWorkspaces();
  const createWorkspace = useCreateWorkspace();
  const deleteWorkspace = useDeleteWorkspace();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null);
  const [confirmText, setConfirmText] = useState("");

  async function handleCreate() {
    if (!name.trim() || createWorkspace.isPending) return;
    await createWorkspace.mutateAsync(name.trim());
    setName("");
    setOpen(false);
  }

  async function handleDelete() {
    if (!deleteTarget || confirmText !== deleteTarget.name) return;
    await deleteWorkspace.mutateAsync(deleteTarget.id);
    setDeleteTarget(null);
    setConfirmText("");
  }

  return (
    <div className="mx-auto max-w-4xl p-8">
      <PageHeader
        title="Workspaces"
        description="Pick a workspace to get started"
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus className="size-4" /> New workspace
          </Button>
        }
      />

      {isLoading && <CardGridSkeleton />}

      {workspaces?.length === 0 ? (
        <EmptyState icon={Building2} title="No workspaces yet" description="Create one to start building." />
      ) : (
        <div key={isLoading ? "loading" : "loaded"} className="animate-fade-in grid grid-cols-1 gap-2.5 sm:grid-cols-2 md:grid-cols-3">
          {workspaces?.map((ws) => (
            <Link key={ws.id} to={`/workspaces/${ws.id}`}>
              <CardLink className="group flex items-center gap-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-accent-secondary-tint">
                  <Building2 className="size-4 text-accent-secondary" strokeWidth={1.75} />
                </div>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink-primary">{ws.name}</span>
                <button
                  type="button"
                  aria-label="Delete workspace"
                  className="shrink-0 rounded p-1 text-ink-tertiary opacity-0 transition-opacity hover:bg-status-danger-tint hover:text-status-danger group-hover:opacity-100 focus-visible:opacity-100"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setDeleteTarget(ws);
                    setConfirmText("");
                  }}
                >
                  <Trash2 className="size-3.5" />
                </button>
              </CardLink>
            </Link>
          ))}
        </div>
      )}

      <Dialog open={open} onClose={() => setOpen(false)} title="New workspace">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Name</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Acme Inc" autoFocus />
        <Button onClick={handleCreate} loading={createWorkspace.isPending} className="mt-4 w-full">
          Create workspace
        </Button>
      </Dialog>

      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)} title="Delete workspace">
        <p className="mb-3 text-sm text-ink-secondary">
          This permanently deletes <span className="font-medium text-ink-primary">{deleteTarget?.name}</span> — every base, table,
          dashboard, automation, and connection in it. This can't be undone.
        </p>
        <label className="mb-1 block text-xs font-medium text-ink-secondary">
          Type <span className="font-mono">{deleteTarget?.name}</span> to confirm
        </label>
        <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} autoFocus />
        <Button
          variant="danger"
          onClick={handleDelete}
          loading={deleteWorkspace.isPending}
          disabled={confirmText !== deleteTarget?.name}
          className="mt-4 w-full"
        >
          Delete workspace
        </Button>
      </Dialog>
    </div>
  );
}
