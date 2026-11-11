import type { ButtonHTMLAttributes } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "../../lib/cn";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "outline";
type Size = "sm" | "md";

// Copper (accent) is spent only on the primary action per screen -- every
// other variant stays neutral so the one thing you're meant to *do* on a
// page never has to compete with things you're only meant to *navigate to*.
const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-accent text-white shadow-sm shadow-accent/20 hover:bg-accent-hover hover:shadow-md hover:shadow-accent/30",
  secondary: "bg-surface text-ink-primary ring-1 ring-inset ring-border-strong hover:bg-surface-raised",
  outline: "bg-transparent text-ink-secondary ring-1 ring-inset ring-border-default hover:bg-surface-raised hover:text-ink-primary",
  danger: "bg-surface text-status-danger ring-1 ring-inset ring-status-danger/30 hover:bg-status-danger-tint",
  ghost: "bg-transparent text-ink-secondary hover:bg-surface-raised hover:text-ink-primary",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "px-2.5 py-1 text-xs gap-1",
  md: "px-3.5 py-2 text-sm gap-1.5",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export function Button({ variant = "primary", size = "md", loading = false, disabled, className, children, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-md font-medium transition-all duration-150 ease-snappy active:scale-[0.97]",
        // A single focus color across every variant reads unambiguously as
        // "keyboard focus" rather than blending into whichever variant's own
        // accent happens to be in play.
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-secondary",
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100",
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className="size-3.5 animate-spin" />}
      {children}
    </button>
  );
}
