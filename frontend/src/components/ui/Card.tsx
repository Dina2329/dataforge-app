import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-lg border border-border-default bg-surface p-4", className)} {...props} />;
}

export function CardLink({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "cursor-pointer rounded-lg border border-border-default bg-surface p-4 transition-all duration-150 ease-snappy",
        "hover:-translate-y-0.5 hover:border-border-strong hover:bg-surface-raised hover:shadow-md active:translate-y-0 active:shadow-sm",
        className,
      )}
      {...props}
    />
  );
}
