import { useRef, useState, type ChangeEvent } from "react";
import { Check, X } from "lucide-react";
import { useImportExcel, useInspectExcel } from "../../hooks/useBases";
import { apiErrorMessage } from "../../lib/apiClient";
import type { ExcelImportResult, ExcelSheetPreview } from "../../types";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";

interface ImportExcelDialogProps {
  baseId: string;
  open: boolean;
  onClose: () => void;
}

/** Upload an .xlsx workbook, pick which sheet(s) to bring in, and name the
 * table each one becomes -- every checked sheet is imported as its own
 * table in one go, same as picking several files would be, just from one
 * workbook. Parsing happens server-side (openpyxl); the browser only ever
 * sees the sheet names/column preview the inspect call returns. */
export function ImportExcelDialog({ baseId, open, onClose }: ImportExcelDialogProps) {
  const inspectExcel = useInspectExcel(baseId);
  const importExcel = useImportExcel(baseId);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sheets, setSheets] = useState<ExcelSheetPreview[] | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [tableNames, setTableNames] = useState<Record<string, string>>({});
  const [results, setResults] = useState<ExcelImportResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setFile(null);
    setSheets(null);
    setSelected({});
    setTableNames({});
    setResults(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0];
    if (!picked) return;
    setFile(picked);
    setResults(null);
    setError(null);
    try {
      const sheetList = await inspectExcel.mutateAsync(picked);
      setSheets(sheetList);
      setSelected(Object.fromEntries(sheetList.map((s) => [s.name, true])));
      setTableNames(Object.fromEntries(sheetList.map((s) => [s.name, s.name])));
    } catch (err) {
      setError(apiErrorMessage(err, "Could not read that file"));
    }
  }

  function toggleSheet(name: string) {
    setSelected((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  const selectedNames = (sheets ?? []).filter((s) => selected[s.name]).map((s) => s.name);

  async function handleImport() {
    if (!file || selectedNames.length === 0) {
      setError("Pick at least one sheet to import");
      return;
    }
    const emptyName = selectedNames.find((name) => !tableNames[name]?.trim());
    if (emptyName) {
      setError(`Give "${emptyName}" a table name`);
      return;
    }
    setError(null);
    const specs = selectedNames.map((name) => ({ sheet_name: name, table_name: tableNames[name].trim() }));
    try {
      const res = await importExcel.mutateAsync({ file, sheets: specs });
      setResults(res);
    } catch {
      // Toasted by the hook's onError -- the dialog stays open on the sheet
      // picker so the user can retry without re-uploading the file.
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Import Excel" size="lg">
      {!sheets && (
        <div className="mb-3">
          <label className="mb-1 block text-xs font-medium text-ink-secondary">Excel file (.xlsx)</label>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
            onChange={handleFileChange}
            className="text-sm text-ink-secondary"
          />
          {inspectExcel.isPending && <p className="mt-2 text-xs text-ink-tertiary">Reading sheets…</p>}
        </div>
      )}

      {sheets && !results && (
        <>
          <p className="mb-3 text-xs text-ink-secondary">
            Pick which sheet(s) to import — each one becomes its own table.
          </p>
          <div className="mb-4 max-h-80 space-y-2 overflow-y-auto">
            {sheets.map((sheet) => (
              <div key={sheet.name} className="flex items-start gap-2.5 rounded-lg border border-border-default p-2.5">
                <input
                  type="checkbox"
                  checked={!!selected[sheet.name]}
                  onChange={() => toggleSheet(sheet.name)}
                  className="mt-3.5 accent-accent-secondary"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs text-ink-tertiary">
                    {sheet.name} — {sheet.columns.length} column{sheet.columns.length === 1 ? "" : "s"}, {sheet.row_count} row
                    {sheet.row_count === 1 ? "" : "s"}
                  </p>
                  <Input
                    value={tableNames[sheet.name] ?? ""}
                    onChange={(e) => setTableNames((prev) => ({ ...prev, [sheet.name]: e.target.value }))}
                    disabled={!selected[sheet.name]}
                    placeholder="Table name"
                    className="mt-1"
                  />
                </div>
              </div>
            ))}
          </div>
          {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
          <div className="flex gap-2">
            <Button variant="secondary" onClick={reset} className="flex-1">
              Choose a different file
            </Button>
            <Button onClick={handleImport} loading={importExcel.isPending} disabled={selectedNames.length === 0} className="flex-1">
              Import {selectedNames.length || ""} sheet{selectedNames.length === 1 ? "" : "s"}
            </Button>
          </div>
        </>
      )}

      {results && (
        <>
          <div className="mb-4 space-y-1.5">
            {results.map((r) => (
              <div key={r.sheet_name} className="flex items-start gap-2 text-sm">
                {r.table ? (
                  <Check className="mt-0.5 size-4 shrink-0 text-status-success" />
                ) : (
                  <X className="mt-0.5 size-4 shrink-0 text-status-danger" />
                )}
                <div className="min-w-0">
                  <span className="text-ink-secondary">{r.table ? r.table.name : r.sheet_name}</span>
                  {r.error && <p className="truncate text-xs text-status-danger">{r.error}</p>}
                </div>
              </div>
            ))}
          </div>
          <Button onClick={handleClose} className="w-full">
            Done
          </Button>
        </>
      )}

      {error && !sheets && <p className="mt-3 text-sm text-status-danger">{error}</p>}
    </Dialog>
  );
}
