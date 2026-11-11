import type { InputHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export function Input({ className, type = "text", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type={type}
      className={cn(
        "w-full rounded-lg border border-border-default bg-surface px-3 py-2 text-sm text-ink-primary placeholder:text-ink-tertiary",
        "outline-none transition-colors focus:border-accent-secondary focus:ring-2 focus:ring-accent-secondary/30",
        "disabled:cursor-not-allowed disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}
