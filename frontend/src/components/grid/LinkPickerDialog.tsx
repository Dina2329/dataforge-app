import { useEffect, useMemo, useState } from "react";
import { useTable } from "../../hooks/useBases";
import { useRecords } from "../../hooks/useRecords";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";

interface LinkPickerDialogProps {
  targetTableId: string;
  selectedRowIds: number[];
  open: boolean;
  onClose: () => void;
  onSave: (rowIds: number[]) => void;
}

export function LinkPickerDialog({ targetTableId, selectedRowIds, open, onClose, onSave }: LinkPickerDialogProps) {
  const { data: table } = useTable(open ? targetTableId : undefined);
  const recordsQuery = useRecords(open ? targetTableId : undefined);
  const [selected, setSelected] = useState<number[]>(selectedRowIds);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (open) {
      setSelected(selectedRowIds);
      setSearch("");
    }
    // Only re-sync when the dialog transitions to open — selectedRowIds
    // itself changes identity on every parent render otherwise.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const primaryField = table?.fields.find((f) => f.is_primary) ?? table?.fields[0];
  const rows = useMemo(() => recordsQuery.data?.pages.flatMap((p) => p.rows) ?? [], [recordsQuery.data]);

  const filtered = rows.filter((row) => {
    if (!search) return true;
    const display = primaryField ? String(row.values[primaryField.name] ?? "") : "";
    return display.toLowerCase().includes(search.toLowerCase());
  });

  function toggle(rowId: number) {
    setSelected((prev) => (prev.includes(rowId) ? prev.filter((id) => id !== rowId) : [...prev, rowId]));
  }

  return (
    <Dialog open={open} onClose={onClose} title={`Link ${table?.name ?? "records"}`}>
      <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search…" className="mb-3" />
      <div className="mb-4 max-h-64 space-y-0.5 overflow-y-auto">
        {filtered.map((row) => {
          const display = primaryField ? String(row.values[primaryField.name] ?? `Row ${row.row_id}`) : `Row ${row.row_id}`;
          const checked = selected.includes(row.row_id);
          return (
            <label
              key={row.row_id}
              className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-ink-secondary hover:bg-surface-raised"
            >
              <input type="checkbox" checked={checked} onChange={() => toggle(row.row_id)} className="size-4" />
              {display}
            </label>
          );
        })}
        {filtered.length === 0 && <p className="px-2 py-4 text-center text-xs text-ink-tertiary">No rows found</p>}
      </div>
      <Button className="w-full" onClick={() => onSave(selected)}>
        Save links
      </Button>
    </Dialog>
  );
}
