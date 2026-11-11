import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FileSpreadsheet, History, Plug, Plus, Table2, Trash2, Upload } from "lucide-react";
import { useCreateTable, useDeleteTable, useImportCsv, useTables } from "../hooks/useBases";
import { useBase } from "../hooks/useDataSources";
import { useWorkspaces } from "../hooks/useWorkspaces";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import { apiErrorMessage } from "../lib/apiClient";
import { Button } from "../components/ui/Button";
import { CardLink } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { Input } from "../components/ui/Input";
import { PageHeader } from "../components/shared/PageHeader";
import { EmptyState } from "../components/shared/EmptyState";
import { CardGridSkeleton } from "../components/ui/Skeleton";
import { ConfirmDeleteDialog } from "../components/shared/ConfirmDeleteDialog";
import { ImportFromSourceDialog } from "../components/connectors/ImportFromSourceDialog";
import { ImportExcelDialog } from "../components/bases/ImportExcelDialog";
import { SnapshotsDialog } from "../components/bases/SnapshotsDialog";
import type { Table } from "../types";

export function TablesPage() {
  const { baseId } = useParams<{ baseId: string }>();
  const { data: base } = useBase(baseId);
  useReportWorkspaceContext(base?.workspace_id);
  const { data: workspaces } = useWorkspaces();
  const workspaceName = workspaces?.find((w) => w.id === base?.workspace_id)?.name;
  const { data: tables, isLoading } = useTables(baseId);
  const createTable = useCreateTable(baseId);
  const deleteTable = useDeleteTable(baseId);
  const importCsv = useImportCsv(baseId);

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [importExcelOpen, setImportExcelOpen] = useState(false);
  const [importSourceOpen, setImportSourceOpen] = useState(false);
  const [importName, setImportName] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Table | null>(null);
  const [snapshotsOpen, setSnapshotsOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleCreate() {
    if (!name.trim() || createTable.isPending) return;
    await createTable.mutateAsync(name.trim());
    setName("");
    setCreateOpen(false);
  }

  async function handleImport() {
    if (importCsv.isPending) return;
    const file = fileInputRef.current?.files?.[0];
    if (!file || !importName.trim()) {
      setImportError("Pick a CSV file and give the table a name");
      return;
    }
    setImportError(null);
    try {
      await importCsv.mutateAsync({ tableName: importName.trim(), file });
      setImportOpen(false);
      setImportName("");
    } catch (err) {
      setImportError(apiErrorMessage(err, "Import failed"));
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    await deleteTable.mutateAsync(deleteTarget.id);
    setDeleteTarget(null);
  }

  return (
    <div className="mx-auto max-w-4xl p-8">
      <PageHeader
        title="Tables"
        breadcrumbs={
          base && workspaceName
            ? [{ label: workspaceName, to: "/" }, { label: base.name, to: `/workspaces/${base.workspace_id}` }, { label: "Tables" }]
            : undefined
        }
        actions={
          <>
            <Button variant="secondary" onClick={() => setSnapshotsOpen(true)}>
              <History className="size-4" /> Snapshots
            </Button>
            <Button variant="secondary" onClick={() => setImportSourceOpen(true)} disabled={!base}>
              <Plug className="size-4" /> Import from connection
            </Button>
            <Button variant="secondary" onClick={() => setImportOpen(true)}>
              <Upload className="size-4" /> Import CSV
            </Button>
            <Button variant="secondary" onClick={() => setImportExcelOpen(true)} disabled={!baseId}>
              <FileSpreadsheet className="size-4" /> Import Excel
            </Button>
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" /> New table
            </Button>
          </>
        }
      />

      {isLoading && <CardGridSkeleton />}

      {tables?.length === 0 ? (
        <EmptyState icon={Table2} title="No tables yet" description="Create one, or import from a CSV or connection." />
      ) : (
        <div key={isLoading ? "loading" : "loaded"} className="animate-fade-in grid grid-cols-1 gap-2.5 sm:grid-cols-2 md:grid-cols-3">
          {tables?.map((table) => (
            <Link key={table.id} to={`/tables/${table.id}`}>
              <CardLink className="group flex items-center gap-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-accent-secondary-tint">
                  <Table2 className="size-4 text-accent-secondary" strokeWidth={1.75} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink-primary">{table.name}</p>
                  <p className="text-xs text-ink-tertiary">{table.fields.length} fields</p>
                </div>
                <button
                  type="button"
                  aria-label="Delete table"
                  className="shrink-0 rounded p-1 text-ink-tertiary opacity-0 transition-opacity hover:bg-status-danger-tint hover:text-status-danger group-hover:opacity-100 focus-visible:opacity-100"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setDeleteTarget(table);
                  }}
                >
                  <Trash2 className="size-3.5" />
                </button>
              </CardLink>
            </Link>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} title="New table">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Name</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Customers" autoFocus />
        <Button onClick={handleCreate} loading={createTable.isPending} className="mt-4 w-full">
          Create table
        </Button>
      </Dialog>

      <Dialog open={importOpen} onClose={() => setImportOpen(false)} title="Import CSV">
        <div className="mb-3">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Table name</label>
          <Input value={importName} onChange={(e) => setImportName(e.target.value)} placeholder="Imported table" />
        </div>
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">CSV file</label>
          <input ref={fileInputRef} type="file" accept=".csv,text/csv" className="text-sm text-ink-secondary" />
        </div>
        {importError && <p className="mb-3 text-sm text-status-danger">{importError}</p>}
        <Button onClick={handleImport} loading={importCsv.isPending} className="w-full">
          Import
        </Button>
      </Dialog>

      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        loading={deleteTable.isPending}
        title="Delete table"
        description={`This permanently deletes "${deleteTarget?.name}" and every row in it. This can't be undone.`}
      />

      {base && baseId && (
        <ImportFromSourceDialog
          workspaceId={base.workspace_id}
          baseId={baseId}
          open={importSourceOpen}
          onClose={() => setImportSourceOpen(false)}
        />
      )}

      {baseId && <SnapshotsDialog baseId={baseId} open={snapshotsOpen} onClose={() => setSnapshotsOpen(false)} />}

      {baseId && <ImportExcelDialog baseId={baseId} open={importExcelOpen} onClose={() => setImportExcelOpen(false)} />}
    </div>
  );
}
