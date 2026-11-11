import type { ReactNode } from "react";
import { Breadcrumbs, type Crumb } from "./Breadcrumbs";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  breadcrumbs?: Crumb[];
}

export function PageHeader({ title, description, actions, breadcrumbs }: PageHeaderProps) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div className="min-w-0">
        {breadcrumbs && breadcrumbs.length > 0 && <Breadcrumbs items={breadcrumbs} />}
        <h1 className="text-lg font-semibold text-ink-primary">{title}</h1>
        {description && <p className="mt-0.5 text-sm text-ink-secondary">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  );
}
