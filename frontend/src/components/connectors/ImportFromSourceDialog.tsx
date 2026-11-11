import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { SYNC_CAPABLE_SOURCE_TYPES, type TableRef } from "../../types";
import { useDataSourceColumns, useDataSourceTables, useDataSources, useImportFromSource } from "../../hooks/useDataSources";
import { apiErrorMessage } from "../../lib/apiClient";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

interface ImportFromSourceDialogProps {
  workspaceId: string;
  baseId: string;
  open: boolean;
  onClose: () => void;
}

export function ImportFromSourceDialog({ workspaceId, baseId, open, onClose }: ImportFromSourceDialogProps) {
  const { data: dataSources } = useDataSources(workspaceId);
  const [sourceId, setSourceId] = useState<string>("");
  const { data: tables } = useDataSourceTables(sourceId || undefined);
  const [selectedTable, setSelectedTable] = useState<TableRef | null>(null);
  const { data: columns } = useDataSourceColumns(sourceId || undefined, selectedTable);
  const [newTableName, setNewTableName] = useState("");
  const [syncEnabled, setSyncEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const importFromSource = useImportFromSource(baseId);

  const selectedSource = dataSources?.find((ds) => ds.id === sourceId);
  const primaryKeyColumns = columns?.filter((c) => c.is_primary_key) ?? [];
  const syncEligible = !!selectedSource && SYNC_CAPABLE_SOURCE_TYPES.has(selectedSource.source_type) && primaryKeyColumns.length === 1;

  useEffect(() => {
    if (dataSources && dataSources.length > 0 && !sourceId) setSourceId(dataSources[0].id);
  }, [dataSources, sourceId]);

  useEffect(() => {
    setSelectedTable(null);
    setNewTableName("");
    setSyncEnabled(false);
  }, [sourceId]);

  useEffect(() => {
    if (!syncEligible) setSyncEnabled(false);
  }, [syncEligible]);

  function handleSelectTable(tableName: string) {
    const table = tables?.find((t) => t.name === tableName) ?? null;
    setSelectedTable(table);
    setNewTableName(table?.name ?? "");
  }

  async function handleImport() {
    if (!sourceId || !selectedTable || !newTableName.trim()) {
      setError("Pick a table and give it a name");
      return;
    }
    setError(null);
    try {
      await importFromSource.mutateAsync({
        dataSourceId: sourceId,
        table: selectedTable,
        newTableName: newTableName.trim(),
        syncEnabled: syncEligible && syncEnabled,
      });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Import failed"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Import from connection">
      {!dataSources || dataSources.length === 0 ? (
        <p className="text-sm text-ink-tertiary">
          No connections yet.{" "}
          <Link to={`/workspaces/${workspaceId}/data-sources`} className="text-accent-secondary underline">
            Add one
          </Link>{" "}
          first.
        </p>
      ) : (
        <>
          <div className="mb-3">
            <label className="mb-1 block text-xs font-medium text-ink-secondary">Connection</label>
            <Select value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
              {dataSources.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.name} ({ds.source_type})
                </option>
              ))}
            </Select>
          </div>

          {tables && (
            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium text-ink-secondary">Table</label>
              <Select value={selectedTable?.name ?? ""} onChange={(e) => handleSelectTable(e.target.value)}>
                <option value="">Select a table…</option>
                {tables.map((t) => (
                  <option key={`${t.schema_name ?? ""}.${t.name}`} value={t.name}>
                    {t.schema_name ? `${t.schema_name}.${t.name}` : t.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {selectedTable && (
            <div className="mb-3">
              <label className="mb-1 block text-xs font-medium text-ink-secondary">New table name</label>
              <Input value={newTableName} onChange={(e) => setNewTableName(e.target.value)} />
              {columns && (
                <p className="mt-1 text-xs text-ink-tertiary">
                  {columns.length} column{columns.length === 1 ? "" : "s"}: {columns.map((c) => c.name).join(", ")}
                </p>
              )}
            </div>
          )}

          {selectedTable && columns && (
            <div className="mb-4">
              <label className={`flex items-start gap-2 text-sm ${syncEligible ? "text-ink-secondary" : "text-ink-tertiary"}`}>
                <input
                  type="checkbox"
                  checked={syncEnabled}
                  disabled={!syncEligible}
                  onChange={(e) => setSyncEnabled(e.target.checked)}
                  className="mt-0.5 accent-accent-secondary disabled:opacity-50"
                />
                <span>
                  Keep this table in sync with the source
                  <span className="block text-xs text-ink-tertiary">
                    {syncEligible
                      ? "Edits made here will be pushed back to the original table. The connection's credentials need write access."
                      : "Not available for this table — sync currently requires PostgreSQL or MySQL with a single primary key column."}
                  </span>
                </span>
              </label>
            </div>
          )}

          {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}

          <Button onClick={handleImport} loading={importFromSource.isPending} disabled={!selectedTable} className="w-full">
            Import
          </Button>
        </>
      )}
    </Dialog>
  );
}
