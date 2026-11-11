import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useToastStore, type ToastVariant } from "../../stores/toastStore";
import { cn } from "../../lib/cn";

const VARIANT_STYLES: Record<ToastVariant, string> = {
  success: "border-status-success/30 [&_.toast-icon]:text-status-success",
  error: "border-status-danger/30 [&_.toast-icon]:text-status-danger",
  info: "border-status-info/30 [&_.toast-icon]:text-status-info",
};

const VARIANT_ICONS: Record<ToastVariant, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
};

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
      {toasts.map((t) => {
        const Icon = VARIANT_ICONS[t.variant];
        return (
          <div
            key={t.id}
            className={cn(
              "animate-toast-in pointer-events-auto flex items-start gap-2 rounded-xl border bg-surface px-3.5 py-3 shadow-lg",
              VARIANT_STYLES[t.variant],
            )}
          >
            <Icon className="toast-icon mt-0.5 size-4 shrink-0" />
            <p className="min-w-0 flex-1 text-sm text-ink-primary">{t.message}</p>
            {t.action && (
              <button
                type="button"
                onClick={() => {
                  t.action!.onClick();
                  dismiss(t.id);
                }}
                className="shrink-0 text-sm font-medium text-accent-secondary hover:opacity-80"
              >
                {t.action.label}
              </button>
            )}
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              className="shrink-0 rounded p-0.5 text-ink-tertiary hover:bg-surface-raised hover:text-ink-secondary"
            >
              <X className="size-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
