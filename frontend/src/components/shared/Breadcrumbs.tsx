import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

export interface Crumb {
  label: string;
  to?: string;
}

/** Real wayfinding (Workspace / Base / Table), not a decorative eyebrow --
 * every segment but the last is a working link back up the hierarchy. */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="mb-1.5 flex min-w-0 items-center gap-1.5 text-xs text-ink-tertiary">
      {items.map((item, i) => (
        <span key={i} className="flex min-w-0 items-center gap-1.5">
          {i > 0 && <ChevronRight className="size-3 shrink-0" />}
          {item.to ? (
            <Link to={item.to} className="truncate transition-colors hover:text-ink-secondary">
              {item.label}
            </Link>
          ) : (
            <span className="truncate text-ink-secondary">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
