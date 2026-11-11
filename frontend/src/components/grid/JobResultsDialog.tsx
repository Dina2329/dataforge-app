import { useMemo, useState } from "react";
import { useImportMissingTermsResults, useMissingTermsJob } from "../../hooks/useMissingTerms";
import type { ImportResultRow } from "../../types";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";

interface JobResultsDialogProps {
  tableId: string;
  jobId: string | null;
  open: boolean;
  onClose: () => void;
}

// Matches the backend's normalize() exactly (missing_terms/service.py):
// trim, collapse internal whitespace, lowercase -- used to build the same
// import-key format the backend stores in a job's imported_keys.
function normalize(value: string): string {
  return value.trim().split(/\s+/).join(" ").toLowerCase();
}

function candidateKey(subDomain: string, termName: string, index: number): string {
  return `${subDomain}\u0001${termName}\u0001${index}`;
}

function cellKey(candidateKeyValue: string, column: string): string {
  return `${candidateKeyValue}\u0001${column}`;
}

/** Opened from the Jobs panel's "View results" for a completed/partially_failed
 * job -- candidates grouped per submitted item, a checkbox per candidate row,
 * a shared column-selection strip (only ticked columns get written; unticked
 * stay empty on the new row). Every ticked candidate always creates its own
 * new row, deliberately with no duplicate check against the main table at
 * all -- some tables are long/EAV-shaped (one row per extracted field of a
 * term, e.g. a "component_name" row and a separate "model_name" row for the
 * same term), where "is this a duplicate" doesn't even make sense the way it
 * would for a wide table. The only thing still prevented is re-importing
 * the exact same (job, candidate) a second time (see imported_keys). Click
 * any (non-imported) cell to edit it in place -- no dedicated Edit button --
 * to correct the API's own output (e.g. an OCR'd page number) before import;
 * sent as per-selection overrides, never mutating the job's own stored
 * response_rows, so the raw API output is still there if the dialog is
 * reopened. */
export function JobResultsDialog({ tableId, jobId, open, onClose }: JobResultsDialogProps) {
  const { data: job } = useMissingTermsJob(jobId ?? undefined, open);
  const importResults = useImportMissingTermsResults(tableId);
  const [checkedRows, setCheckedRows] = useState<Set<string>>(new Set());
  const [checkedColumns, setCheckedColumns] = useState<Set<string> | null>(null);
  const [results, setResults] = useState<ImportResultRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Per-candidate edits of the API's own output, keyed by candidateKey ->
  // {column: editedValue} -- overrides what gets written on import without
  // touching the job's stored response_rows (the raw API output stays
  // visible/re-editable if the dialog is reopened).
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({});
  // Which single cell is mid-edit, as `${candidateKey}\u0001${column}` --
  // click a cell to edit it in place, no dedicated Edit button needed.
  const [editingCell, setEditingCell] = useState<string | null>(null);

  function displayValue(key: string, col: string, candidate: Record<string, unknown>): string {
    const edited = edits[key]?.[col];
    if (edited !== undefined) return edited;
    return candidate[col] == null ? "" : String(candidate[col]);
  }

  function setEditValue(key: string, col: string, value: string) {
    setEdits((prev) => ({ ...prev, [key]: { ...prev[key], [col]: value } }));
  }

  const allColumns = useMemo(() => {
    const cols = new Set<string>();
    for (const group of job?.response_rows ?? []) {
      for (const candidate of group.candidates) Object.keys(candidate).forEach((c) => cols.add(c));
    }
    return Array.from(cols);
  }, [job]);

  const activeColumns = checkedColumns ?? new Set(allColumns);

  function toggleColumn(col: string) {
    setCheckedColumns((prev) => {
      const next = new Set(prev ?? allColumns);
      if (next.has(col)) next.delete(col);
      else next.add(col);
      return next;
    });
  }

  function toggleRow(key: string) {
    setCheckedRows((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function selectAll() {
    const keys = new Set<string>();
    for (const group of job?.response_rows ?? []) {
      group.candidates.forEach((_, i) => keys.add(candidateKey(group.sub_domain, group.term_name, i)));
    }
    setCheckedRows(keys);
  }

  async function handleImport() {
    if (!jobId || !job) return;
    setError(null);
    const selections = [];
    for (const group of job.response_rows ?? []) {
      for (let i = 0; i < group.candidates.length; i++) {
        const key = candidateKey(group.sub_domain, group.term_name, i);
        if (!checkedRows.has(key)) continue;
        const overrides = edits[key];
        selections.push({
          sub_domain: group.sub_domain,
          term_name: group.term_name,
          candidate_index: i,
          columns: Array.from(activeColumns),
          ...(overrides && Object.keys(overrides).length > 0 ? { overrides } : {}),
        });
      }
    }
    if (selections.length === 0) {
      setError("Check at least one row to import");
      return;
    }
    try {
      const imported = await importResults.mutateAsync({ jobId, selections });
      setResults(imported);
    } catch {
      setError("Could not import the selected rows");
    }
  }

  function handleClose() {
    setCheckedRows(new Set());
    setCheckedColumns(null);
    setResults(null);
    setError(null);
    setEdits({});
    setEditingCell(null);
    onClose();
  }

  const alreadyImported = new Set(job?.imported_keys ?? []);

  return (
    <Dialog open={open} onClose={handleClose} title="Review results" size="lg">
      {!job && <p className="text-sm text-ink-secondary">Loading…</p>}

      {job && !results && (
        <>
          <div className="mb-3">
            <label className="mb-1 block text-xs font-medium text-ink-secondary">Columns to write</label>
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {allColumns.map((col) => (
                <label key={col} className="flex items-center gap-1 text-xs text-ink-secondary">
                  <input type="checkbox" checked={activeColumns.has(col)} onChange={() => toggleColumn(col)} className="accent-accent-secondary" />
                  {col}
                </label>
              ))}
            </div>
          </div>

          <div className="mb-3 flex items-center justify-end text-xs text-ink-secondary">
            <Button variant="secondary" size="sm" onClick={selectAll}>
              Select all
            </Button>
          </div>

          {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}

          <div className="mb-4 max-h-96 space-y-3 overflow-y-auto">
            {(job.response_rows ?? []).map((group) => (
              <div key={`${group.sub_domain}\u0001${group.term_name}`} className="rounded-lg border border-border-default p-2.5">
                <p className="mb-2 text-xs font-medium text-ink-primary">
                  {group.sub_domain} / {group.term_name}
                </p>
                <table className="w-full border-collapse text-xs">
                  <thead>
                    <tr>
                      <th className="px-1 py-1" />
                      {allColumns.map((c) => (
                        <th key={c} className="px-2 py-1 text-left font-medium text-ink-tertiary">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {group.candidates.map((candidate, i) => {
                      const key = candidateKey(group.sub_domain, group.term_name, i);
                      const imported = alreadyImported.has(`${normalize(group.sub_domain)}|${normalize(group.term_name)}|${i}`);
                      return (
                        <tr key={key} className="border-t border-border-default">
                          <td className="px-1 py-1">
                            <input type="checkbox" checked={checkedRows.has(key)} disabled={imported} onChange={() => toggleRow(key)} className="accent-accent-secondary" />
                          </td>
                          {allColumns.map((c) => {
                            const cKey = cellKey(key, c);
                            if (editingCell === cKey) {
                              return (
                                <td key={c} className="px-1 py-1">
                                  <input
                                    autoFocus
                                    value={displayValue(key, c, candidate)}
                                    onChange={(e) => setEditValue(key, c, e.target.value)}
                                    onBlur={() => setEditingCell(null)}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter" || e.key === "Escape") setEditingCell(null);
                                    }}
                                    className="w-24 rounded border border-border-default bg-surface px-1.5 py-0.5 text-xs text-ink-primary"
                                  />
                                </td>
                              );
                            }
                            return (
                              <td
                                key={c}
                                onClick={() => !imported && setEditingCell(cKey)}
                                title={imported ? undefined : "Click to edit"}
                                className={`max-w-[10rem] truncate px-2 py-1 text-ink-secondary ${imported ? "" : "cursor-text hover:bg-surface-raised"}`}
                              >
                                {displayValue(key, c, candidate)}
                              </td>
                            );
                          })}
                          {imported && <td className="px-2 py-1 text-ink-tertiary">(already imported)</td>}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          <Button onClick={handleImport} loading={importResults.isPending} className="w-full">
            Import selected
          </Button>
        </>
      )}

      {results && (
        <>
          <div className="mb-4 space-y-1 text-xs">
            {results.map((r, i) => (
              <div key={i} className="flex items-center justify-between rounded border border-border-default px-2 py-1.5">
                <span>
                  {r.sub_domain} / {r.term_name}
                </span>
                <span className="text-ink-tertiary">{r.status}{r.row_id ? ` (row #${r.row_id})` : ""}</span>
              </div>
            ))}
          </div>
          <Button onClick={handleClose} className="w-full">
            Close
          </Button>
        </>
      )}
    </Dialog>
  );
}
