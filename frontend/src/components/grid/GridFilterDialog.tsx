import { useEffect, useState } from "react";
import { useUpdateView } from "../../hooks/useBases";
import type { Field, View } from "../../types";
import { filterExprToRows, NON_FILTERABLE_TYPES, rowsToFilterExpr, type FilterRow } from "../../lib/filterHelpers";
import { apiErrorMessage } from "../../lib/apiClient";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { FilterRowsEditor } from "../shared/FilterRowsEditor";

interface GridFilterDialogProps {
  tableId: string;
  view: View;
  fields: Field[];
  open: boolean;
  onClose: () => void;
}

export function GridFilterDialog({ tableId, view, fields, open, onClose }: GridFilterDialogProps) {
  const filterableFields = fields.filter((f) => !NON_FILTERABLE_TYPES.has(f.field_type));
  const updateView = useUpdateView(tableId);
  const [rows, setRows] = useState<FilterRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setRows(filterExprToRows(view.config.filter));
    setError(null);
  }, [open, view]);

  async function handleApply() {
    setError(null);
    const filter = rowsToFilterExpr(rows, filterableFields);
    try {
      await updateView.mutateAsync({ viewId: view.id, config: { ...view.config, filter } });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not apply filter"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Filter rows">
      <FilterRowsEditor fields={filterableFields} rows={rows} onChange={setRows} emptyMessage="No filters yet — every row is shown." />

      {error && <p className="mb-3 mt-3 text-sm text-status-danger">{error}</p>}
      <Button onClick={handleApply} loading={updateView.isPending} className="mt-3 w-full">
        Apply
      </Button>
    </Dialog>
  );
}
