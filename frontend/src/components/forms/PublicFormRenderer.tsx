import { useState } from "react";
import type { PublicForm, PublicFormField } from "../../types";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

interface PublicFormRendererProps {
  form: PublicForm;
  onSubmit: (values: Record<string, unknown>) => Promise<void> | void;
  submitting?: boolean;
  submitLabel?: string;
}

function FieldInput({ field, value, onChange }: { field: PublicFormField; value: unknown; onChange: (value: unknown) => void }) {
  if (field.field_type === "boolean") {
    return <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} className="size-4" />;
  }
  if (field.field_type === "long_text") {
    return (
      <textarea
        value={typeof value === "string" ? value : ""}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        className="w-full rounded-lg border border-border-default bg-surface px-3 py-2 text-sm text-ink-primary outline-none transition-colors focus:border-accent-secondary focus:ring-2 focus:ring-accent-secondary/30"
      />
    );
  }
  if (field.field_type === "single_select") {
    const choices = field.options.choices ?? [];
    return (
      <Select value={typeof value === "string" ? value : ""} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">—</option>
        {choices.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </Select>
    );
  }
  return (
    <Input
      type={field.field_type === "number" ? "number" : field.field_type === "date" ? "date" : "text"}
      value={value == null ? "" : String(value)}
      onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
    />
  );
}

export function PublicFormRenderer({ form, onSubmit, submitting, submitLabel = "Submit" }: PublicFormRendererProps) {
  const [values, setValues] = useState<Record<string, unknown>>({});

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(values);
      }}
      className="space-y-4"
    >
      {form.fields.map((field) => (
        <div key={field.id}>
          <label className="mb-1 block text-sm font-medium text-ink-secondary">
            {field.name}
            {field.required && <span className="text-status-danger"> *</span>}
          </label>
          <FieldInput
            field={field}
            value={values[field.name]}
            onChange={(value) => setValues((prev) => ({ ...prev, [field.name]: value }))}
          />
        </div>
      ))}
      <Button type="submit" loading={submitting} className="w-full">
        {submitLabel}
      </Button>
    </form>
  );
}
