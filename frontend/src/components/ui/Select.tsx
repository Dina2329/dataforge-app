import type { SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "../../lib/cn";

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select
        className={cn(
          "w-full appearance-none rounded-lg border border-border-default bg-surface px-3 py-2 pr-8 text-sm text-ink-primary",
          "outline-none transition-colors focus:border-accent-secondary focus:ring-2 focus:ring-accent-secondary/30",
          "disabled:cursor-not-allowed disabled:opacity-60",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-tertiary" />
    </div>
  );
}
