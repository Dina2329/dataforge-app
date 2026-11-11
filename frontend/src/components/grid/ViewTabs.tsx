import { useState } from "react";
import { FileText, LayoutGrid, Plus, Table2, Trash2 } from "lucide-react";
import { useDeleteView } from "../../hooks/useBases";
import type { Field, View } from "../../types";
import { AddViewDialog } from "./AddViewDialog";
import { cn } from "../../lib/cn";

const VIEW_ICONS = { grid: Table2, kanban: LayoutGrid, form: FileText } as const;

interface ViewTabsProps {
  tableId: string;
  views: View[];
  fields: Field[];
  activeViewId: string;
  onSelect: (viewId: string) => void;
}

export function ViewTabs({ tableId, views, fields, activeViewId, onSelect }: ViewTabsProps) {
  const [addOpen, setAddOpen] = useState(false);
  const deleteView = useDeleteView(tableId);

  return (
    <div className="mb-3 flex items-center gap-1 border-b border-border-default">
      {views.map((view) => {
        const Icon = VIEW_ICONS[view.view_type] ?? Table2;
        const active = view.id === activeViewId;
        return (
          <div key={view.id} className="group relative">
            <button
              type="button"
              onClick={() => onSelect(view.id)}
              className={cn(
                "flex items-center gap-1.5 rounded-t-lg px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-accent-secondary-tint text-accent-secondary"
                  : "text-ink-tertiary hover:bg-surface-raised hover:text-ink-secondary",
              )}
            >
              <Icon className="size-3.5" />
              {view.name}
            </button>
            {views.length > 1 && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  deleteView.mutate(view.id);
                }}
                aria-label="Delete view"
                className="absolute -right-1 -top-1 hidden rounded-full bg-surface p-0.5 text-ink-tertiary shadow-sm border border-border-default hover:text-status-danger group-hover:block"
              >
                <Trash2 className="size-2.5" />
              </button>
            )}
          </div>
        );
      })}
      <button
        type="button"
        onClick={() => setAddOpen(true)}
        className="ml-1 flex items-center gap-1 rounded-t-lg px-2.5 py-2 text-xs font-medium text-ink-tertiary hover:bg-surface-raised hover:text-ink-secondary"
      >
        <Plus className="size-3.5" /> View
      </button>

      <AddViewDialog tableId={tableId} fields={fields} open={addOpen} onClose={() => setAddOpen(false)} onCreated={onSelect} />
    </div>
  );
}
