import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Building2, Database, History, LayoutDashboard, LogOut, Plug, Search, Table2, Users } from "lucide-react";
import { useWorkspaces } from "../../hooks/useWorkspaces";
import { useBases } from "../../hooks/useBases";
import { useDashboards, useWorkspaceTables } from "../../hooks/useDashboards";
import { useAuthStore } from "../../stores/authStore";
import { cn } from "../../lib/cn";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  workspaceId: string | null;
}

interface PaletteItem {
  id: string;
  label: string;
  group: string;
  icon: typeof Database;
  onSelect: () => void;
}

const GROUP_ORDER = ["Workspaces", "Bases", "Tables", "Dashboards", "Go to", "Actions"];

export function CommandPalette({ open, onClose, workspaceId }: CommandPaletteProps) {
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: workspaces } = useWorkspaces();
  const { data: bases } = useBases(open ? (workspaceId ?? undefined) : undefined);
  const { data: tables } = useWorkspaceTables(open ? (workspaceId ?? undefined) : undefined);
  const { data: dashboards } = useDashboards(open ? (workspaceId ?? undefined) : undefined);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActiveIndex(0);
    const frame = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  const items = useMemo<PaletteItem[]>(() => {
    const list: PaletteItem[] = [];
    workspaces?.forEach((ws) =>
      list.push({
        id: `ws-${ws.id}`,
        label: ws.name,
        group: "Workspaces",
        icon: Building2,
        onSelect: () => navigate(`/workspaces/${ws.id}`),
      }),
    );
    if (workspaceId) {
      bases?.forEach((b) =>
        list.push({ id: `base-${b.id}`, label: b.name, group: "Bases", icon: Database, onSelect: () => navigate(`/bases/${b.id}`) }),
      );
      tables?.forEach((t) =>
        list.push({ id: `table-${t.id}`, label: t.name, group: "Tables", icon: Table2, onSelect: () => navigate(`/tables/${t.id}`) }),
      );
      dashboards?.forEach((d) =>
        list.push({
          id: `dash-${d.id}`,
          label: d.name,
          group: "Dashboards",
          icon: LayoutDashboard,
          onSelect: () => navigate(`/dashboards/${d.id}`),
        }),
      );
      list.push(
        {
          id: "act-datasources",
          label: "Data sources",
          group: "Go to",
          icon: Plug,
          onSelect: () => navigate(`/workspaces/${workspaceId}/data-sources`),
        },
        {
          id: "act-members",
          label: "Members",
          group: "Go to",
          icon: Users,
          onSelect: () => navigate(`/workspaces/${workspaceId}/members`),
        },
        {
          id: "act-audit",
          label: "Audit log",
          group: "Go to",
          icon: History,
          onSelect: () => navigate(`/workspaces/${workspaceId}/audit-log`),
        },
      );
    }
    list.push({
      id: "act-logout",
      label: "Log out",
      group: "Actions",
      icon: LogOut,
      onSelect: () => {
        logout();
        navigate("/login");
      },
    });
    return list;
  }, [workspaces, bases, tables, dashboards, workspaceId, navigate, logout]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => item.label.toLowerCase().includes(q));
  }, [items, query]);

  const grouped = useMemo(() => {
    const map = new Map<string, PaletteItem[]>();
    for (const item of filtered) {
      if (!map.has(item.group)) map.set(item.group, []);
      map.get(item.group)!.push(item);
    }
    return GROUP_ORDER.map((g) => [g, map.get(g) ?? []] as const).filter(([, groupItems]) => groupItems.length > 0);
  }, [filtered]);

  function handleSelect(item: PaletteItem) {
    item.onSelect();
    onClose();
  }

  useEffect(() => setActiveIndex(0), [query]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const item = filtered[activeIndex];
        if (item) handleSelect(item);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, filtered, activeIndex, onClose]);

  if (!open) return null;

  let runningIndex = -1;

  return createPortal(
    <div
      className="animate-dialog-backdrop fixed inset-0 z-50 flex items-start justify-center bg-ink-primary/40 pt-[12vh] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="animate-dialog-panel w-full max-w-lg overflow-hidden rounded-2xl border border-border-default bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-border-default px-4 py-3">
          <Search className="size-4 shrink-0 text-ink-tertiary" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search bases, tables, dashboards…"
            className="w-full border-0 bg-transparent text-sm text-ink-primary outline-none placeholder:text-ink-tertiary"
          />
          <kbd className="shrink-0 rounded border border-border-default px-1.5 py-0.5 text-[10px] font-medium text-ink-tertiary">
            Esc
          </kbd>
        </div>
        <div className="max-h-80 overflow-y-auto p-2">
          {grouped.length === 0 ? (
            <p className="px-2 py-6 text-center text-sm text-ink-tertiary">No results</p>
          ) : (
            grouped.map(([group, groupItems]) => (
              <div key={group} className="mb-1 last:mb-0">
                <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-ink-tertiary">{group}</p>
                {groupItems.map((item) => {
                  runningIndex += 1;
                  const isActive = runningIndex === activeIndex;
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onMouseEnter={() => setActiveIndex(runningIndex)}
                      onClick={() => handleSelect(item)}
                      className={cn(
                        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
                        isActive ? "bg-accent-secondary-tint text-accent-secondary" : "text-ink-secondary hover:bg-surface-raised",
                      )}
                    >
                      <Icon className="size-4 shrink-0 text-ink-tertiary" />
                      <span className="truncate">{item.label}</span>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
