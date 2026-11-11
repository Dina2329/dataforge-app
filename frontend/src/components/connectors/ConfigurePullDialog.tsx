import { useEffect, useState } from "react";
import type { Field } from "../../types";
import { useConfigurePull } from "../../hooks/useDataSources";
import { apiErrorMessage } from "../../lib/apiClient";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

const DEFAULT_POLL_MINUTES = 5;
const DEFAULT_DELETION_MINUTES = 15;

interface ConfigurePullDialogProps {
  tableId: string;
  fields: Field[];
  currentColumn: string | null;
  currentPollIntervalSeconds: number | null;
  currentDeletionIntervalSeconds: number | null;
  open: boolean;
  onClose: () => void;
}

export function ConfigurePullDialog({
  tableId,
  fields,
  currentColumn,
  currentPollIntervalSeconds,
  currentDeletionIntervalSeconds,
  open,
  onClose,
}: ConfigurePullDialogProps) {
  const configurePull = useConfigurePull(tableId);
  // The server does the authoritative native-type check (a plain DATE
  // column is rejected even though it shares this same coarse "date"
  // category) -- this filter is just a client-side head start on picking a
  // plausible column.
  const dateFields = fields.filter((f) => f.field_type === "date");

  const [column, setColumn] = useState(currentColumn ?? "");
  const [pollMinutes, setPollMinutes] = useState(String(Math.round((currentPollIntervalSeconds ?? DEFAULT_POLL_MINUTES * 60) / 60)));
  const [checkDeletions, setCheckDeletions] = useState(currentDeletionIntervalSeconds != null);
  const [deletionMinutes, setDeletionMinutes] = useState(
    String(Math.round((currentDeletionIntervalSeconds ?? DEFAULT_DELETION_MINUTES * 60) / 60)),
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setColumn(currentColumn ?? "");
    setPollMinutes(String(Math.round((currentPollIntervalSeconds ?? DEFAULT_POLL_MINUTES * 60) / 60)));
    setCheckDeletions(currentDeletionIntervalSeconds != null);
    setDeletionMinutes(String(Math.round((currentDeletionIntervalSeconds ?? DEFAULT_DELETION_MINUTES * 60) / 60)));
    setError(null);
  }, [open, currentColumn, currentPollIntervalSeconds, currentDeletionIntervalSeconds]);

  async function handleSave() {
    setError(null);
    const pollSeconds = Math.max(60, (Number(pollMinutes) || DEFAULT_POLL_MINUTES) * 60);
    const deletionSeconds = checkDeletions ? Math.max(300, (Number(deletionMinutes) || DEFAULT_DELETION_MINUTES) * 60) : null;
    try {
      await configurePull.mutateAsync({
        externalUpdatedAtColumn: column || null,
        pollIntervalSeconds: column ? pollSeconds : null,
        deletionCheckIntervalSeconds: column ? deletionSeconds : null,
      });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not save pull settings"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Pull changes from source">
      <p className="mb-3 text-sm text-ink-secondary">
        Periodically check the source for edits and new rows made outside DataForge, and bring them in. When both sides
        changed the same row, the source's value wins and you'll be notified.
      </p>

      <div className="mb-3">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">"Last modified" column</label>
        {dateFields.length === 0 ? (
          <p className="text-xs text-status-warning">
            This table has no date/timestamp field to track changes by — pulling isn't available.
          </p>
        ) : (
          <Select value={column} onChange={(e) => setColumn(e.target.value)}>
            <option value="">Off (push only)</option>
            {dateFields.map((f) => (
              <option key={f.id} value={f.name}>
                {f.name}
              </option>
            ))}
          </Select>
        )}
      </div>

      {column && (
        <>
          <div className="mb-3">
            <label className="mb-1 block text-xs font-medium text-ink-secondary">Check for changes every (minutes)</label>
            <Input type="number" min={1} value={pollMinutes} onChange={(e) => setPollMinutes(e.target.value)} />
          </div>
          <label className="mb-3 flex items-center gap-2 text-sm text-ink-secondary">
            <input
              type="checkbox"
              checked={checkDeletions}
              onChange={(e) => setCheckDeletions(e.target.checked)}
              className="accent-accent-secondary"
            />
            Also detect rows deleted at the source
          </label>
          {checkDeletions && (
            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium text-ink-secondary">Check for deletions every (minutes)</label>
              <Input type="number" min={5} value={deletionMinutes} onChange={(e) => setDeletionMinutes(e.target.value)} />
            </div>
          )}
        </>
      )}

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
      <Button onClick={handleSave} loading={configurePull.isPending} className="w-full">
        Save
      </Button>
    </Dialog>
  );
}
