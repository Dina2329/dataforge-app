import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../lib/apiClient";
import { Input } from "../ui/Input";

interface DistinctValuePickerProps {
  fieldId: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

/** Suggests values already used in this field's own table (and, if the field
 * has exclude_values_from configured, leaves out ones already present in the
 * mapped field too) -- a suggestion, not an enforced enum, so it's a plain
 * text input with a <datalist> of candidates rather than a closed <Select>:
 * the person filtering can still type a value that isn't in the list.
 * Deliberately separate from shared/FieldValueInput, which every other
 * filter/automation/bulk-update surface uses and already has better,
 * type-specific pickers for boolean/single_select/date/number -- this is
 * only for free-text fields, where today's blank input gives no hint of
 * what values actually exist. */
export function DistinctValuePicker({ fieldId, value, onChange, className }: DistinctValuePickerProps) {
  const { data } = useQuery({
    queryKey: ["filter-values", fieldId],
    queryFn: async () => (await apiClient.get<{ values: unknown[] }>(`/api/fields/${fieldId}/filter-values`)).data.values,
  });
  const listId = `distinct-values-${fieldId}`;

  return (
    <>
      <Input value={value} onChange={(e) => onChange(e.target.value)} list={listId} placeholder="value…" className={className} />
      <datalist id={listId}>
        {(data ?? []).map((v) => (
          <option key={String(v)} value={String(v)} />
        ))}
      </datalist>
    </>
  );
}
