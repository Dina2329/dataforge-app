import { useRef, useState, type ChangeEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Download, Layers, Plus, Sparkles, Trash2, Upload } from "lucide-react";
import { useBases, useCreateBase, useDeleteBase, useExportBase, useImportBase } from "../hooks/useBases";
import { useWorkspaces } from "../hooks/useWorkspaces";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import { apiClient, apiErrorMessage } from "../lib/apiClient";
import { toast } from "../stores/toastStore";
import { Button } from "../components/ui/Button";
import { CardLink } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { Input } from "../components/ui/Input";
import { PageHeader } from "../components/shared/PageHeader";
import { EmptyState } from "../components/shared/EmptyState";
import { CardGridSkeleton } from "../components/ui/Skeleton";
import { ConfirmDeleteDialog } from "../components/shared/ConfirmDeleteDialog";
import type { Base } from "../types";

const SAMPLE_STATUS_CHOICES = [
  { value: "todo", label: "Todo" },
  { value: "in_progress", label: "In Progress" },
  { value: "done", label: "Done" },
];
const SAMPLE_PRIORITY_CHOICES = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];
const SAMPLE_ROWS = [
  { Name: "Design landing page", Status: "done", Priority: "high", Due: "2026-01-10" },
  { Name: "Write launch announcement", Status: "in_progress", Priority: "high", Due: "2026-01-15" },
  { Name: "Set up analytics", Status: "todo", Priority: "medium", Due: "2026-01-18" },
  { Name: "QA pass on checkout", Status: "in_progress", Priority: "high", Due: "2026-01-12" },
  { Name: "Prepare support docs", Status: "todo", Priority: "low", Due: "2026-01-20" },
  { Name: "Social media teasers", Status: "done", Priority: "medium", Due: "2026-01-08" },
];

export function BasesPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  useReportWorkspaceContext(workspaceId);
  const { data: workspaces } = useWorkspaces();
  const workspaceName = workspaces?.find((w) => w.id === workspaceId)?.name;
  const { data: bases, isLoading } = useBases(workspaceId);
  const createBase = useCreateBase(workspaceId);
  const deleteBase = useDeleteBase(workspaceId);
  const exportBase = useExportBase();
  const importBase = useImportBase(workspaceId);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Base | null>(null);
  const [sampleLoading, setSampleLoading] = useState(false);

  // Pure orchestration over the same REST endpoints the rest of the app
  // already uses (no new backend surface) -- a first-run workspace has
  // nothing to click into or explore, so this exists purely to give a new
  // user something real to poke at instead of an empty grid.
  async function handleTrySampleData() {
    if (!workspaceId || sampleLoading) return;
    setSampleLoading(true);
    try {
      const base = (await apiClient.post(`/api/workspaces/${workspaceId}/bases`, { name: "Product Launch (Sample)" })).data;
      const table = (await apiClient.post(`/api/bases/${base.id}/tables`, { name: "Tasks" })).data;
      await apiClient.post(`/api/tables/${table.id}/fields`, {
        name: "Status",
        field_type: "single_select",
        options: { choices: SAMPLE_STATUS_CHOICES },
      });
      await apiClient.post(`/api/tables/${table.id}/fields`, {
        name: "Priority",
        field_type: "single_select",
        options: { choices: SAMPLE_PRIORITY_CHOICES },
      });
      await apiClient.post(`/api/tables/${table.id}/fields`, { name: "Due", field_type: "date", options: {} });
      for (const values of SAMPLE_ROWS) {
        await apiClient.post(`/api/tables/${table.id}/rows`, { values });
      }
      queryClient.invalidateQueries({ queryKey: ["bases", workspaceId] });
      toast.success('Created sample base "Product Launch (Sample)"');
      navigate(`/tables/${table.id}`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not create sample data"));
    } finally {
      setSampleLoading(false);
    }
  }

  async function handleCreate() {
    if (!name.trim() || createBase.isPending) return;
    await createBase.mutateAsync(name.trim());
    setName("");
    setOpen(false);
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    await deleteBase.mutateAsync(deleteTarget.id);
    setDeleteTarget(null);
  }

  async function handleImportFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setImportError(null);
    try {
      await importBase.mutateAsync(file);
    } catch (err) {
      setImportError(apiErrorMessage(err, "Could not import base"));
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-8">
      <PageHeader
        title="Bases"
        description="Group related tables together"
        breadcrumbs={workspaceName ? [{ label: workspaceName, to: "/" }, { label: "Bases" }] : undefined}
        actions={
          <>
            <input ref={fileInputRef} type="file" accept=".json" className="hidden" onChange={handleImportFile} />
            <Button variant="secondary" loading={importBase.isPending} onClick={() => fileInputRef.current?.click()}>
              <Upload className="size-4" /> Import base
            </Button>
            <Button onClick={() => setOpen(true)}>
              <Plus className="size-4" /> New base
            </Button>
          </>
        }
      />

      {importError && <p className="mb-4 text-sm text-status-danger">{importError}</p>}

      {isLoading && <CardGridSkeleton />}

      {bases?.length === 0 ? (
        <EmptyState
          icon={Layers}
          title="No bases yet"
          description="Create one to start adding tables, or try it out with sample data first."
          action={
            <Button variant="secondary" loading={sampleLoading} onClick={handleTrySampleData}>
              <Sparkles className="size-4" /> Try with sample data
            </Button>
          }
        />
      ) : (
        <div key={isLoading ? "loading" : "loaded"} className="animate-fade-in grid grid-cols-1 gap-2.5 sm:grid-cols-2 md:grid-cols-3">
          {bases?.map((base) => (
            <Link key={base.id} to={`/bases/${base.id}`}>
              <CardLink className="group flex items-center gap-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-accent-secondary-tint">
                  <Layers className="size-4 text-accent-secondary" strokeWidth={1.75} />
                </div>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink-primary">{base.name}</span>
                <button
                  type="button"
                  aria-label="Export base"
                  className="shrink-0 rounded p-1 text-ink-tertiary opacity-0 transition-opacity hover:bg-surface-raised hover:text-ink-secondary group-hover:opacity-100 focus-visible:opacity-100"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    exportBase.mutate({ baseId: base.id, baseName: base.name });
                  }}
                >
                  <Download className="size-3.5" />
                </button>
                <button
                  type="button"
                  aria-label="Delete base"
                  className="shrink-0 rounded p-1 text-ink-tertiary opacity-0 transition-opacity hover:bg-status-danger-tint hover:text-status-danger group-hover:opacity-100 focus-visible:opacity-100"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setDeleteTarget(base);
                  }}
                >
                  <Trash2 className="size-3.5" />
                </button>
              </CardLink>
            </Link>
          ))}
        </div>
      )}

      <Dialog open={open} onClose={() => setOpen(false)} title="New base">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Name</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Product Data" autoFocus />
        <Button onClick={handleCreate} loading={createBase.isPending} className="mt-4 w-full">
          Create base
        </Button>
      </Dialog>

      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        loading={deleteBase.isPending}
        title="Delete base"
        description={`This permanently deletes "${deleteTarget?.name}" and every table and row inside it. This can't be undone.`}
      />
    </div>
  );
}
