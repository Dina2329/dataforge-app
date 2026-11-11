import { useEffect, useState } from "react";
import { useRecordSubmitConfig, useUpsertRecordSubmitConfig } from "../../hooks/useRecordSubmit";
import { apiErrorMessage } from "../../lib/apiClient";
import type { Field } from "../../types";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

const STATUS_FIELD_TYPES = new Set(["date", "text", "long_text"]);

interface SubmitConfigDialogProps {
  tableId: string;
  fields: Field[];
  open: boolean;
  onClose: () => void;
}

/** Configures the external "Submit row" target for a table -- styled after
 * the automations send_webhook action's own URL input (AddActionDialog.tsx),
 * plus an optional headers box and a status field to stamp on success. */
export function SubmitConfigDialog({ tableId, fields, open, onClose }: SubmitConfigDialogProps) {
  const { data: config } = useRecordSubmitConfig(open ? tableId : undefined);
  const upsertConfig = useUpsertRecordSubmitConfig(tableId);
  const [url, setUrl] = useState("");
  const [headersText, setHeadersText] = useState("");
  const [statusFieldId, setStatusFieldId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const statusFieldOptions = fields.filter((f) => STATUS_FIELD_TYPES.has(f.field_type));

  useEffect(() => {
    if (!open) return;
    setUrl(config?.url ?? "");
    setHeadersText(config?.headers ? JSON.stringify(config.headers, null, 2) : "");
    setStatusFieldId(config?.status_field_id ?? statusFieldOptions[0]?.id ?? "");
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, config]);

  async function handleSubmit() {
    if (!url.trim()) {
      setError("Give a URL");
      return;
    }
    if (!statusFieldId) {
      setError("Choose a field to stamp on success");
      return;
    }
    let headers: Record<string, string> | null = null;
    if (headersText.trim()) {
      try {
        headers = JSON.parse(headersText);
      } catch {
        setError("Headers must be valid JSON (e.g. {\"Authorization\": \"Bearer ...\"})");
        return;
      }
    }
    setError(null);

    try {
      await upsertConfig.mutateAsync({ url: url.trim(), headers, status_field_id: statusFieldId });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not save submit settings"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Submit settings">
      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">External API URL</label>
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/hook" />
      </div>

      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Headers (optional, JSON)</label>
        <textarea
          value={headersText}
          onChange={(e) => setHeadersText(e.target.value)}
          rows={3}
          placeholder='{"Authorization": "Bearer ..."}'
          className="w-full rounded-lg border border-border-default bg-surface px-3 py-2 font-mono text-xs text-ink-primary outline-none transition-colors focus:border-accent-secondary focus:ring-2 focus:ring-accent-secondary/30"
        />
      </div>

      <div className="mb-4">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Stamp this field on success</label>
        {statusFieldOptions.length === 0 ? (
          <p className="text-xs text-status-warning">Add a text or date field first to track submission status.</p>
        ) : (
          <Select value={statusFieldId} onChange={(e) => setStatusFieldId(e.target.value)}>
            {statusFieldOptions.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </Select>
        )}
      </div>

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
      <Button onClick={handleSubmit} loading={upsertConfig.isPending} disabled={statusFieldOptions.length === 0} className="w-full">
        Save
      </Button>
    </Dialog>
  );
}
