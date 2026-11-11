import { cn } from "../../lib/cn";

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  "aria-label"?: string;
}

export function Switch({ checked, onChange, disabled, "aria-label": ariaLabel }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-150 ease-snappy",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-secondary",
        "disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "bg-accent" : "bg-border-strong",
      )}
    >
      <span
        className={cn(
          "inline-block size-3.5 rounded-full bg-white shadow-sm transition-transform duration-150 ease-snappy",
          checked ? "translate-x-[18px]" : "translate-x-1",
        )}
      />
    </button>
  );
}
