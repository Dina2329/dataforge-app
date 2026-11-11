import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  size?: "md" | "lg";
}

const SIZE_CLASSES: Record<NonNullable<DialogProps["size"]>, string> = {
  md: "max-w-md",
  lg: "max-w-2xl",
};

export function Dialog({ open, onClose, title, children, size = "md" }: DialogProps) {
  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;
  // Portalled to <body> rather than rendered in place: position:fixed is
  // relative to the nearest ancestor with a `transform` (CSS spec), and grid
  // cells render inside react-virtual rows that translateY() on every row —
  // without the portal, a dialog opened from a grid cell renders clipped to
  // that row instead of centered in the viewport.
  return createPortal(
    <div
      className="animate-dialog-backdrop fixed inset-0 z-50 flex items-center justify-center bg-ink-primary/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className={`animate-dialog-panel w-full ${SIZE_CLASSES[size]} rounded-2xl border border-border-default bg-surface p-6 shadow-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-ink-primary">{title}</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-ink-tertiary transition-colors hover:bg-surface-raised hover:text-ink-secondary"
          >
            <X className="size-4" />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
