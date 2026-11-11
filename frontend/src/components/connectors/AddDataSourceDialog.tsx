import { useRef, useState } from "react";
import { SOURCE_TYPES, type SourceType } from "../../types";
import { useCreateDataSource } from "../../hooks/useDataSources";
import { apiErrorMessage } from "../../lib/apiClient";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  postgres: "PostgreSQL",
  mysql: "MySQL",
  sqlite: "SQLite (file upload)",
  elasticsearch: "Elasticsearch",
};

const DEFAULT_PORTS: Record<SourceType, number | null> = {
  postgres: 5432,
  mysql: 3306,
  sqlite: null,
  elasticsearch: null,
};

interface AddDataSourceDialogProps {
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}

export function AddDataSourceDialog({ workspaceId, open, onClose }: AddDataSourceDialogProps) {
  const createDataSource = useCreateDataSource(workspaceId);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("postgres");
  const [host, setHost] = useState("");
  const [port, setPort] = useState<string>(String(DEFAULT_PORTS.postgres));
  const [database, setDatabase] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [url, setUrl] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setName("");
    setHost("");
    setDatabase("");
    setUsername("");
    setPassword("");
    setUrl("");
    setFileName(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    setError(null);
  }

  async function handleSubmit() {
    if (!name.trim()) {
      setError("Give the connection a name");
      return;
    }
    setError(null);

    try {
      if (sourceType === "sqlite") {
        const file = fileInputRef.current?.files?.[0];
        if (!file) {
          setError("Choose a .sqlite file to upload");
          return;
        }
        await createDataSource.mutateAsync({ name: name.trim(), sourceType, config: {}, file });
      } else if (sourceType === "elasticsearch") {
        if (!url.trim()) {
          setError("The cluster URL is required");
          return;
        }
        const config: Record<string, unknown> = { url: url.trim() };
        if (username.trim()) config.username = username.trim();
        if (password) config.password = password;
        await createDataSource.mutateAsync({ name: name.trim(), sourceType, config });
      } else {
        if (!host.trim() || !database.trim() || !username.trim()) {
          setError("Host, database, and username are required");
          return;
        }
        await createDataSource.mutateAsync({
          name: name.trim(),
          sourceType,
          config: { host: host.trim(), port: Number(port), database: database.trim(), username: username.trim(), password },
        });
      }
      reset();
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not create connection"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Add data source">
      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Connection name</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Production Postgres" />
      </div>

      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Type</label>
        <Select
          value={sourceType}
          onChange={(e) => {
            const next = e.target.value as SourceType;
            setSourceType(next);
            setPort(String(DEFAULT_PORTS[next] ?? ""));
          }}
        >
          {SOURCE_TYPES.map((type) => (
            <option key={type} value={type}>
              {SOURCE_TYPE_LABELS[type]}
            </option>
          ))}
        </Select>
      </div>

      {sourceType === "sqlite" ? (
        <div className="mb-4">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">SQLite file</label>
          <div className="flex items-center gap-2">
            <label
              htmlFor="sqlite-file-input"
              className="inline-flex shrink-0 cursor-pointer items-center justify-center rounded-md bg-surface px-3.5 py-2 text-sm font-medium text-ink-primary ring-1 ring-inset ring-border-strong transition-colors hover:bg-surface-raised"
            >
              Choose file
            </label>
            <input
              id="sqlite-file-input"
              ref={fileInputRef}
              type="file"
              accept=".sqlite,.db,.sqlite3"
              className="hidden"
              onChange={(e) => setFileName(e.target.files?.[0]?.name ?? null)}
            />
            <span className="min-w-0 flex-1 truncate text-sm text-ink-tertiary">{fileName ?? "No file chosen"}</span>
          </div>
        </div>
      ) : sourceType === "elasticsearch" ? (
        <>
          <div className="mb-3">
            <label className="mb-1 block text-xs font-medium text-ink-secondary">Cluster URL</label>
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://localhost:9200" />
          </div>
          <div className="mb-4 flex gap-2">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-ink-secondary">Username (optional)</label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-ink-secondary">Password (optional)</label>
              <Input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="mb-3 flex gap-2">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-ink-secondary">Host</label>
              <Input value={host} onChange={(e) => setHost(e.target.value)} placeholder="localhost" />
            </div>
            <div className="w-24">
              <label className="mb-1 block text-xs font-medium text-ink-secondary">Port</label>
              <Input value={port} onChange={(e) => setPort(e.target.value)} type="number" />
            </div>
          </div>
          <div className="mb-3">
            <label className="mb-1 block text-xs font-medium text-ink-secondary">Database</label>
            <Input value={database} onChange={(e) => setDatabase(e.target.value)} />
          </div>
          <div className="mb-3 flex gap-2">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-ink-secondary">Username</label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-ink-secondary">Password</label>
              <Input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
            </div>
          </div>
        </>
      )}

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}

      <Button onClick={handleSubmit} loading={createDataSource.isPending} className="w-full">
        Add connection
      </Button>
    </Dialog>
  );
}
