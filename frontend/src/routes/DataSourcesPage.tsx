import { useState } from "react";
import { ArrowLeft, CheckCircle2, Database, Plug, XCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { useDataSources, useDeleteDataSource, useTestDataSource } from "../hooks/useDataSources";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import { apiErrorMessage } from "../lib/apiClient";
import { AddDataSourceDialog } from "../components/connectors/AddDataSourceDialog";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/shared/PageHeader";
import { EmptyState } from "../components/shared/EmptyState";
import { ListRowsSkeleton } from "../components/ui/Skeleton";

export function DataSourcesPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  useReportWorkspaceContext(workspaceId);
  const navigate = useNavigate();
  const { data: dataSources, isLoading } = useDataSources(workspaceId);
  const deleteDataSource = useDeleteDataSource(workspaceId);
  const testDataSource = useTestDataSource();

  const [addOpen, setAddOpen] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; message: string } | "pending">>({});

  async function handleTest(id: string) {
    setTestResults((prev) => ({ ...prev, [id]: "pending" }));
    try {
      await testDataSource.mutateAsync(id);
      setTestResults((prev) => ({ ...prev, [id]: { ok: true, message: "Connected" } }));
    } catch (err) {
      setTestResults((prev) => ({ ...prev, [id]: { ok: false, message: apiErrorMessage(err, "Connection failed") } }));
    }
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
        title="Data sources"
        description="Connect PostgreSQL, MySQL, SQLite, or Elasticsearch to import data"
        actions={<Button onClick={() => setAddOpen(true)}>+ Add connection</Button>}
      />

      {isLoading && <ListRowsSkeleton count={3} />}

      {dataSources?.length === 0 ? (
        <EmptyState icon={Plug} title="No connections yet" description="Add a PostgreSQL, MySQL, SQLite, or Elasticsearch source." />
      ) : (
        <div key={isLoading ? "loading" : "loaded"} className="animate-fade-in space-y-2">
          {dataSources?.map((ds) => {
            const result = testResults[ds.id];
            return (
              <Card key={ds.id} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-secondary-tint">
                    <Database className="size-4 text-accent-secondary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-ink-primary">{ds.name}</p>
                    <Badge tone="neutral" dot={false}>{ds.source_type}</Badge>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {result && result !== "pending" && (
                    <span className={`flex items-center gap-1 text-xs ${result.ok ? "text-status-success" : "text-status-danger"}`}>
                      {result.ok ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />}
                      {result.message}
                    </span>
                  )}
                  <Button variant="secondary" size="sm" loading={result === "pending"} onClick={() => handleTest(ds.id)}>
                    Test
                  </Button>
                  <Button variant="danger" size="sm" onClick={() => deleteDataSource.mutate(ds.id)}>
                    Delete
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {workspaceId && <AddDataSourceDialog workspaceId={workspaceId} open={addOpen} onClose={() => setAddOpen(false)} />}
    </div>
  );
}
