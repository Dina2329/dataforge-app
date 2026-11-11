import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

type Tone = "neutral" | "accent" | "success" | "warning" | "info" | "danger";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-surface-raised text-ink-secondary ring-border-strong/60",
  accent: "bg-accent-tint text-accent ring-accent/25",
  success: "bg-status-success-tint text-status-success ring-status-success/25",
  warning: "bg-status-warning-tint text-status-warning ring-status-warning/25",
  info: "bg-status-info-tint text-status-info ring-status-info/25",
  danger: "bg-status-danger-tint text-status-danger ring-status-danger/25",
};

const DOT_CLASSES: Record<Tone, string> = {
  neutral: "bg-ink-tertiary",
  accent: "bg-accent",
  success: "bg-status-success",
  warning: "bg-status-warning",
  info: "bg-status-info",
  danger: "bg-status-danger",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  /** A colored dot never stands alone as the only signal (the label text is
   * always present too), but it gives dense chip-heavy views — the grid,
   * the members list — a scannable shape to pattern-match on before reading
   * the word. Set false for chips where the tone is purely categorical
   * (e.g. a connector type) rather than a state. */
  dot?: boolean;
}

export function Badge({ tone = "neutral", dot = true, className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        TONE_CLASSES[tone],
        className,
      )}
      {...props}
    >
      {dot && <span className={cn("size-1.5 shrink-0 rounded-full", DOT_CLASSES[tone])} />}
      {children}
    </span>
  );
}
