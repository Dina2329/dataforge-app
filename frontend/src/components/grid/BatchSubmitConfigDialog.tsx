import { useEffect, useState } from "react";
import { useBatchSubmitConfig, useUpsertBatchSubmitConfig } from "../../hooks/useBatchSubmit";
import { apiErrorMessage } from "../../lib/apiClient";
import { emptyFilterRow, filterExprToRows, NON_FILTERABLE_TYPES, rowsToFilterExpr, type FilterRow } from "../../lib/filterHelpers";
import type { Field, FilterExpr } from "../../types";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { FilterRowsEditor } from "../shared/FilterRowsEditor";

const MIN_BATCH_SIZE = 1;
const MAX_BATCH_SIZE = 1000;

interface BatchSubmitConfigDialogProps {
  tableId: string;
  fields: Field[];
  open: boolean;
  onClose: () => void;
}

/** Configures the external "Send batch to API" target for a table --
 * deliberately separate from Submit settings (its own URL/headers), plus
 * which rows are "ready to send" (any condition, same filter language as the
 * grid's own Filter dialog -- a boolean "Ready" checkbox is just the simplest
 * case of it) and how many rows go in each outbound request. Clicking "Send
 * batch" (DataGrid toolbar) sends every currently-matching row, chunked to
 * this batch size -- matching rows are NOT auto-cleared after a successful
 * send, so re-clicking Send resends everything that still matches. */
export function BatchSubmitConfigDialog({ tableId, fields, open, onClose }: BatchSubmitConfigDialogProps) {
  const { data: config } = useBatchSubmitConfig(open ? tableId : undefined);
  const upsertConfig = useUpsertBatchSubmitConfig(tableId);
  const filterableFields = fields.filter((f) => !NON_FILTERABLE_TYPES.has(f.field_type));
  const [url, setUrl] = useState("");
  const [headersText, setHeadersText] = useState("");
  const [rows, setRows] = useState<FilterRow[]>([]);
  const [batchSize, setBatchSize] = useState(100);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setUrl(config?.url ?? "");
    setHeadersText(config?.headers ? JSON.stringify(config.headers, null, 2) : "");
    const hasFilter = !!config?.filter && Object.keys(config.filter).length > 0;
    setRows(hasFilter ? filterExprToRows(config!.filter as FilterExpr) : [emptyFilterRow(filterableFields[0]?.name ?? "")]);
    setBatchSize(config?.batch_size ?? 100);
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, config]);

  async function handleSubmit() {
    if (!url.trim()) {
      setError("Give a URL");
      return;
    }
    const filter = rowsToFilterExpr(rows, filterableFields);
    if (!filter) {
      setError("Add at least one condition for which rows are ready to send");
      return;
    }
    if (!Number.isInteger(batchSize) || batchSize < MIN_BATCH_SIZE || batchSize > MAX_BATCH_SIZE) {
      setError(`Batch size must be a whole number between ${MIN_BATCH_SIZE} and ${MAX_BATCH_SIZE}`);
      return;
    }
    let headers: Record<string, string> | null = null;
    if (headersText.trim()) {
      try {
        headers = JSON.parse(headersText);
      } catch {
        setError('Headers must be valid JSON (e.g. {"Authorization": "Bearer ..."})');
        return;
      }
    }
    setError(null);

    try {
      await upsertConfig.mutateAsync({ url: url.trim(), headers, filter, batch_size: batchSize });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not save Batch Submit settings"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Batch Submit settings">
      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">External API URL</label>
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/batch" />
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

      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Rows ready to send</label>
        <FilterRowsEditor fields={filterableFields} rows={rows} onChange={setRows} emptyMessage="Add at least one condition." />
      </div>

      <div className="mb-4">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">Rows per batch</label>
        <Input
          type="number"
          min={MIN_BATCH_SIZE}
          max={MAX_BATCH_SIZE}
          value={batchSize}
          onChange={(e) => setBatchSize(Number(e.target.value))}
        />
        <p className="mt-1 text-xs text-ink-tertiary">
          E.g. 1,000 marked rows at a batch size of 100 sends as 10 separate requests, 100 rows each.
        </p>
      </div>

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
      <Button onClick={handleSubmit} loading={upsertConfig.isPending} className="w-full">
        Save
      </Button>
    </Dialog>
  );
}
