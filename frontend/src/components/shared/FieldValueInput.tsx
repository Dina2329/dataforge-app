import type { Field } from "../../types";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

interface FieldValueInputProps {
  field: Field | undefined;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  disabled?: boolean;
}

/** A value editor that matches whatever the target field actually is —
 * a checkbox-style dropdown for boolean, that field's real choices for
 * single_select, a date picker for date, a number input for number — rather
 * than one generic text box asking the user to remember and type the right
 * raw representation for every field type. Shared by every place that either
 * filters on a field's value (automation triggers, bulk update, row-level
 * policies) or sets one (automation actions, bulk update). */
export function FieldValueInput({ field, value, onChange, className, disabled }: FieldValueInputProps) {
  if (field?.field_type === "boolean") {
    return (
      <Select value={value} onChange={(e) => onChange(e.target.value)} className={className} disabled={disabled}>
        <option value="">Choose…</option>
        <option value="true">Checked</option>
        <option value="false">Unchecked</option>
      </Select>
    );
  }
  if (field?.field_type === "single_select") {
    const choices = (field.options.choices ?? []) as { value: string; label: string }[];
    return (
      <Select value={value} onChange={(e) => onChange(e.target.value)} className={className} disabled={disabled}>
        <option value="">Choose…</option>
        {choices.map((c) => (
          <option key={c.value} value={c.value}>
            {c.label}
          </option>
        ))}
      </Select>
    );
  }
  if (field?.field_type === "date") {
    return (
      <Input type="date" value={value} onChange={(e) => onChange(e.target.value)} className={className} disabled={disabled} />
    );
  }
  if (field?.field_type === "number") {
    return (
      <Input
        type="number"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="0"
        className={className}
        disabled={disabled}
      />
    );
  }
  return (
    <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder="value" className={className} disabled={disabled} />
  );
}
