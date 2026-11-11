import type { ComponentType, ReactNode } from "react";

interface EmptyStateProps {
  icon: ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border-strong py-14 text-center">
      <div className="mb-3 flex size-12 items-center justify-center rounded-full bg-accent-secondary-tint">
        <Icon className="size-5 text-accent-secondary" />
      </div>
      <p className="text-sm font-medium text-ink-secondary">{title}</p>
      {description && <p className="mt-1 max-w-xs text-xs text-ink-tertiary">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
