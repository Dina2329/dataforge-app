import { cn } from "../../lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-border-default", className)} />;
}

export function CardGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-lg border border-border-default bg-surface p-4">
          <Skeleton className="size-9 shrink-0 rounded-lg" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ))}
    </div>
  );
}

export function ListRowsSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-lg border border-border-default bg-surface p-4">
          <Skeleton className="size-9 shrink-0 rounded-lg" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-1/3" />
            <Skeleton className="h-3 w-1/5" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function TableRowsSkeleton({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border-default bg-surface">
      <div className="border-b border-border-default bg-surface-raised px-3 py-2.5">
        <Skeleton className="h-3 w-24" />
      </div>
      <div className="divide-y divide-border-default">
        {Array.from({ length: rows }, (_, r) => (
          <div key={r} className="flex items-center gap-4 px-3 py-3">
            {Array.from({ length: cols }, (_, c) => (
              <Skeleton key={c} className="h-3 flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
