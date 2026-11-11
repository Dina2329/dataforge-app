import { useEffect, useState } from "react";
import { useMissingTermsConfig, useUpsertMissingTermsConfig } from "../../hooks/useMissingTerms";
import { apiErrorMessage } from "../../lib/apiClient";
import type { Field } from "../../types";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

const EXCLUDED_FIELD_TYPES = new Set(["link_to_record", "lookup", "rollup", "formula", "attachment"]);

const SLOTS: { key: string; label: string; required: boolean }[] = [
  { key: "sub_domain", label: "Sub-Domain", required: true },
  { key: "term_name", label: "Term Name", required: true },
  { key: "page", label: "Page", required: false },
  { key: "pdf_image", label: "PDF/Image", required: false },
  { key: "pdf_name", label: "PDF Name", required: false },
  { key: "keywords", label: "Keywords", required: false },
];

interface MissingTermsConfigDialogProps {
  tableId: string;
  fields: Field[];
  open: boolean;
  onClose: () => void;
}

/** Per-table opt-in: this table's own Estate/Building/Unit scope (all
 * optional -- narrows which rows of the workspace's one shared prerequest
 * list this table compares against) plus the field mapping every slot the
 * feature needs (Sub-Domain/Term Name required before it can be used at
 * all; Page/PDF-Image/Keywords optional) needs to land in a real field on
 * this table. */
export function MissingTermsConfigDialog({ tableId, fields, open, onClose }: MissingTermsConfigDialogProps) {
  const { data: config } = useMissingTermsConfig(open ? tableId : undefined);
  const upsertConfig = useUpsertMissingTermsConfig(tableId);
  const [estate, setEstate] = useState("");
  const [building, setBuilding] = useState("");
  const [unit, setUnit] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const tableFields = fields.filter((f) => !EXCLUDED_FIELD_TYPES.has(f.field_type));

  useEffect(() => {
    if (!open) return;
    setEstate(config?.estate ?? "");
    setBuilding(config?.building ?? "");
    setUnit(config?.unit ?? "");
    setMapping(config?.field_mapping ?? {});
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, config]);

  async function handleSubmit() {
    const missingRequired = SLOTS.filter((s) => s.required && !mapping[s.key]);
    if (missingRequired.length > 0) {
      setError(`Map a field for: ${missingRequired.map((s) => s.label).join(", ")}`);
      return;
    }
    setError(null);
    try {
      await upsertConfig.mutateAsync({
        estate: estate.trim() || null,
        building: building.trim() || null,
        unit: unit.trim() || null,
        field_mapping: mapping,
      });
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not save Missing Terms config"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Missing Terms config" size="lg">
      <p className="mb-3 text-xs text-ink-secondary">
        Optional scope -- narrows the shared prerequest list down to just this Estate/Building/Unit. A prerequest row that doesn't specify
        one of these itself still shows up here (using this scope as its tag); only a row that specifies a *different* value is excluded.
        Leave blank to compare against the whole list.
      </p>
      <div className="mb-4 grid grid-cols-3 gap-2">
        <Input value={estate} onChange={(e) => setEstate(e.target.value)} placeholder="Estate" />
        <Input value={building} onChange={(e) => setBuilding(e.target.value)} placeholder="Building" />
        <Input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="Unit" />
      </div>

      <label className="mb-1 block text-xs font-medium text-ink-secondary">Field mapping</label>
      <div className="mb-4 space-y-2">
        {SLOTS.map((slot) => (
          <div key={slot.key} className="flex items-center gap-2">
            <span className="w-24 shrink-0 text-xs text-ink-secondary">
              {slot.label}
              {slot.required && <span className="text-status-danger"> *</span>}
            </span>
            <Select value={mapping[slot.key] ?? ""} onChange={(e) => setMapping((prev) => ({ ...prev, [slot.key]: e.target.value }))} className="flex-1">
              <option value="">— no field —</option>
              {tableFields.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </Select>
          </div>
        ))}
      </div>

      {error && <p className="mb-3 text-sm text-status-danger">{error}</p>}
      <Button onClick={handleSubmit} loading={upsertConfig.isPending} className="w-full">
        Save
      </Button>
    </Dialog>
  );
}
