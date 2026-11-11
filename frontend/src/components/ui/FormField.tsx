import type { ReactNode } from "react";

interface FormFieldProps {
  label: string;
  htmlFor?: string;
  required?: boolean;
  help?: string;
  error?: string;
  children: ReactNode;
}

export function FormField({ label, htmlFor, required, help, error, children }: FormFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-xs font-medium text-ink-secondary">
        {label}
        {required && <span className="ml-0.5 text-status-danger">*</span>}
      </label>
      {children}
      {error ? (
        <p className="text-xs text-status-danger">{error}</p>
      ) : help ? (
        <p className="text-xs text-ink-tertiary">{help}</p>
      ) : null}
    </div>
  );
}
