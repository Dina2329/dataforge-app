import { Dialog } from "../ui/Dialog";

const SHORTCUTS: { keys: string[]; description: string }[] = [
  { keys: ["⌘", "K"], description: "Open search / command palette" },
  { keys: ["?"], description: "Show this shortcuts panel" },
  { keys: ["Esc"], description: "Close a dialog or the command palette" },
  { keys: ["↑", "↓", "←", "→"], description: "Move the active grid cell" },
  { keys: ["Shift", "↑", "↓", "←", "→"], description: "Extend the cell selection into a range" },
  { keys: ["Tab"], description: "Move to the next cell" },
  { keys: ["Shift", "Tab"], description: "Move to the previous cell" },
  { keys: ["Enter"], description: "Commit an edit and move down a row" },
  { keys: ["⌘", "C"], description: "Copy the active cell or selected range" },
  { keys: ["⌘", "V"], description: "Paste into the active cell or range" },
  { keys: ["⌘", "Z"], description: "Undo the last cell edit" },
];

export function KeyboardShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="Keyboard shortcuts">
      <ul className="flex flex-col gap-2.5">
        {SHORTCUTS.map((s, i) => (
          <li key={i} className="flex items-center justify-between gap-4">
            <span className="text-sm text-ink-secondary">{s.description}</span>
            <span className="flex shrink-0 items-center gap-1">
              {s.keys.map((k, j) => (
                <kbd
                  key={j}
                  className="rounded border border-border-default bg-surface-raised px-1.5 py-0.5 text-[11px] font-medium text-ink-secondary"
                >
                  {k}
                </kbd>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </Dialog>
  );
}
