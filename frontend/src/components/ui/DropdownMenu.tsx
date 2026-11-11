import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "../../lib/cn";

interface DropdownMenuProps {
  trigger: ReactNode;
  children: ReactNode;
  align?: "left" | "right";
  /** "top" opens the panel above the trigger instead of below -- for a
   * trigger that sits at the bottom of the viewport (e.g. the sidebar's
   * footer icons), the default "bottom" would render mostly or entirely
   * past the window edge with nothing to scroll it into view. */
  side?: "bottom" | "top";
  /** Extra classes on the trigger button itself -- e.g. "w-full min-w-0" so
   * a trigger holding variable-length content (a user's email) can actually
   * truncate instead of forcing the whole row wider than its container. */
  triggerClassName?: string;
}

export function DropdownMenu({ trigger, children, align = "right", side = "bottom", triggerClassName }: DropdownMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    // A scrolled-away trigger leaves its panel visually orphaned -- still
    // correctly anchored (it's a descendant of whatever scrolled), but now
    // floating somewhere the user never asked for, where it can overlap a
    // different trigger's panel if that one's opened next. Scroll doesn't
    // bubble, but a capture-phase listener on document still sees it fire on
    // any descendant scrollable element (e.g. the data grid's horizontally
    // scrolling body), not just window-level scrolling.
    function handleScroll() {
      setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("scroll", handleScroll, true);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("scroll", handleScroll, true);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn("flex items-center gap-2 rounded-lg p-1 transition-colors hover:bg-surface-raised", triggerClassName)}
      >
        {trigger}
      </button>
      {open && (
        <div
          className={cn(
            "animate-dialog-panel absolute z-50 min-w-[180px] rounded-xl border border-border-default bg-surface p-1 shadow-lg",
            align === "right" ? "right-0" : "left-0",
            side === "top" ? "bottom-full mb-1" : "mt-1",
          )}
          onClick={() => setOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  );
}

export function DropdownItem({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(
        "flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm text-ink-secondary transition-colors hover:bg-surface-raised hover:text-ink-primary",
        className,
      )}
      {...props}
    />
  );
}
