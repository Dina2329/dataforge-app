import { Loader2 } from "lucide-react";

export function PageSpinner() {
  return (
    <div className="flex h-full min-h-[50vh] flex-1 items-center justify-center p-8">
      <Loader2 className="size-5 animate-spin text-ink-tertiary" />
    </div>
  );
}
