import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Bell, Database, History, Keyboard, LayoutDashboard, ListChecks, LogOut, PanelLeft, PanelLeftClose, Plug, Search, Users } from "lucide-react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../../stores/authStore";
import { useWorkspaceContextStore } from "../../stores/workspaceContextStore";
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications } from "../../hooks/useNotifications";
import { Avatar } from "../ui/Avatar";
import { DropdownItem, DropdownMenu } from "../ui/DropdownMenu";
import { CommandPalette } from "./CommandPalette";
import { KeyboardShortcutsDialog } from "./KeyboardShortcutsDialog";
import { ThemeToggle } from "./ThemeToggle";
import { cn } from "../../lib/cn";

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(ms / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function NotificationBell() {
  const navigate = useNavigate();
  const { data } = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();
  const unreadCount = data?.unread_count ?? 0;

  return (
    <DropdownMenu
      align="left"
      side="top"
      trigger={
        <span className="relative flex size-7 items-center justify-center rounded-md text-ink-tertiary transition-colors hover:bg-surface-raised hover:text-ink-secondary">
          <Bell className="size-4" />
          {unreadCount > 0 && (
            <span className="absolute right-0.5 top-0.5 flex size-3.5 items-center justify-center rounded-full bg-status-danger text-[9px] font-semibold text-white">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </span>
      }
    >
      <div className="flex items-center justify-between px-2.5 py-1.5">
        <span className="text-xs font-semibold text-ink-primary">Notifications</span>
        {unreadCount > 0 && (
          <button type="button" onClick={() => markAllRead.mutate()} className="text-xs text-accent-secondary hover:opacity-80">
            Mark all read
          </button>
        )}
      </div>
      <div className="max-h-80 min-w-72 overflow-y-auto">
        {!data || data.notifications.length === 0 ? (
          <p className="px-2.5 py-4 text-center text-xs text-ink-tertiary">No notifications yet.</p>
        ) : (
          data.notifications.map((n) => (
            <button
              key={n.id}
              type="button"
              className={cn(
                "flex w-full flex-col items-start gap-0.5 rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-surface-raised",
                !n.is_read && "bg-accent-secondary-tint",
              )}
              onClick={() => {
                if (!n.is_read) markRead.mutate(n.id);
                if (n.link) navigate(n.link);
              }}
            >
              <span className="font-medium text-ink-primary">{n.title}</span>
              <span className="line-clamp-2 text-xs text-ink-tertiary">{n.message}</span>
              <span className="text-[10px] text-ink-tertiary">{timeAgo(n.created_at)}</span>
            </button>
          ))
        )}
      </div>
    </DropdownMenu>
  );
}

function NavLink({
  to,
  icon: Icon,
  label,
  active,
  itemRef,
  collapsed,
}: {
  to: string;
  icon: typeof Database;
  label: string;
  active: boolean;
  itemRef: (el: HTMLAnchorElement | null) => void;
  collapsed: boolean;
}) {
  return (
    <Link
      ref={itemRef}
      to={to}
      title={collapsed ? label : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-r-md border-l-2 border-transparent py-1.5 pr-2.5 text-sm font-medium transition-colors",
        collapsed ? "justify-center pl-2.5" : "pl-3",
        active ? "bg-accent-tint text-ink-primary" : "text-ink-secondary hover:bg-surface-raised hover:text-ink-primary",
      )}
    >
      <Icon className="size-4 shrink-0" strokeWidth={1.75} />
      {!collapsed && label}
    </Link>
  );
}

const SIDEBAR_COLLAPSED_KEY = "df-sidebar-collapsed";

function readStoredCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  } catch {
    return false;
  }
}

export function AppLayout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const location = useLocation();
  const workspaceId = useWorkspaceContextStore((s) => s.currentWorkspaceId);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const navRefs = useRef(new Map<string, HTMLAnchorElement>());
  const [indicator, setIndicator] = useState<{ top: number; height: number } | null>(null);
  // Sidebar is per-viewer chrome, not shared app state -- localStorage is the
  // right place for it, and the whole-table grid is exactly what wants the
  // extra width this buys back.
  const [collapsed, setCollapsed] = useState(readStoredCollapsed);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed));
    } catch {
      // Private-browsing/storage-blocked -- the toggle still works for this
      // session, it just won't persist across reloads.
    }
  }, [collapsed]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((open) => !open);
        return;
      }
      // "?" opens the shortcuts cheat sheet -- but not while the user is
      // actually typing a literal "?" into a text field.
      const target = e.target as HTMLElement | null;
      const isTyping = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable;
      if (e.key === "?" && !isTyping) {
        e.preventDefault();
        setShortcutsOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const navItems = workspaceId
    ? [
        {
          to: `/workspaces/${workspaceId}`,
          icon: Database,
          label: "Bases",
          active: (path: string) => path === `/workspaces/${workspaceId}` || path.startsWith("/bases/") || path.startsWith("/tables/"),
        },
        {
          to: `/workspaces/${workspaceId}/dashboards`,
          icon: LayoutDashboard,
          label: "Dashboards",
          active: (path: string) => path === `/workspaces/${workspaceId}/dashboards` || path.startsWith("/dashboards/"),
        },
        {
          to: `/workspaces/${workspaceId}/data-sources`,
          icon: Plug,
          label: "Data sources",
          active: (path: string) => path === `/workspaces/${workspaceId}/data-sources`,
        },
        {
          to: `/workspaces/${workspaceId}/members`,
          icon: Users,
          label: "Members",
          active: (path: string) => path === `/workspaces/${workspaceId}/members`,
        },
        {
          to: `/workspaces/${workspaceId}/audit-log`,
          icon: History,
          label: "Audit log",
          active: (path: string) => path === `/workspaces/${workspaceId}/audit-log`,
        },
        {
          to: `/workspaces/${workspaceId}/prerequest`,
          icon: ListChecks,
          label: "Prerequest list",
          active: (path: string) => path === `/workspaces/${workspaceId}/prerequest`,
        },
      ]
    : [];

  const activeTo = navItems.find((item) => item.active(location.pathname))?.to ?? null;

  useLayoutEffect(() => {
    const el = activeTo ? navRefs.current.get(activeTo) : null;
    if (!el) {
      setIndicator(null);
      return;
    }
    setIndicator({ top: el.offsetTop, height: el.offsetHeight });
  }, [activeTo]);

  return (
    <div className="flex h-screen bg-canvas">
      <aside
        className={cn(
          "flex shrink-0 flex-col overflow-hidden border-r border-border-default bg-surface transition-[width] duration-200 ease-snappy",
          collapsed ? "w-14" : "w-56",
        )}
      >
        <Link
          to="/"
          className={cn(
            "flex items-center gap-2 px-4 py-4 text-[13px] font-semibold tracking-tight text-ink-primary",
            collapsed && "justify-center px-0",
          )}
        >
          <span className="flex size-5 shrink-0 items-center justify-center rounded-[5px] bg-accent text-[11px] font-bold text-white">
            D
          </span>
          {!collapsed && "DataForge"}
        </Link>

        <div className={cn("px-2.5 pb-2.5", collapsed ? "flex justify-center" : "flex justify-end")}>
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="rounded-md p-1 text-ink-tertiary transition-colors hover:bg-surface-raised hover:text-ink-secondary"
          >
            {collapsed ? <PanelLeft className="size-4" /> : <PanelLeftClose className="size-4" />}
          </button>
        </div>

        <div className="px-2.5 pb-2.5">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            title={collapsed ? "Search (⌘K)" : undefined}
            className={cn(
              "flex w-full items-center gap-2 rounded-md py-1.5 text-sm text-ink-tertiary ring-1 ring-inset ring-border-default transition-colors hover:bg-surface-raised hover:text-ink-secondary",
              collapsed ? "justify-center px-1.5" : "px-2.5",
            )}
          >
            <Search className="size-3.5 shrink-0" />
            {!collapsed && (
              <>
                Search
                <kbd className="ml-auto rounded border border-border-default bg-surface-raised px-1 py-0.5 text-[10px] font-medium text-ink-tertiary">
                  ⌘K
                </kbd>
              </>
            )}
          </button>
        </div>

        <nav className="relative flex-1 space-y-0.5 px-2.5">
          {indicator && (
            <div
              className="absolute left-2.5 w-0.5 rounded-full bg-accent transition-all duration-200 ease-snappy"
              style={{ top: indicator.top, height: indicator.height }}
            />
          )}
          {navItems.map(({ active, ...item }) => (
            <NavLink
              key={item.to}
              {...item}
              active={active(location.pathname)}
              collapsed={collapsed}
              itemRef={(el) => {
                if (el) navRefs.current.set(item.to, el);
                else navRefs.current.delete(item.to);
              }}
            />
          ))}
        </nav>

        <div className="flex flex-col gap-2 border-t border-border-default p-2.5">
          {/* Its own row, full width -- a long email needs real room to
             truncate into, and sharing a row with the icons below squeezed
             them out of the sidebar entirely for anything but a short one. */}
          <DropdownMenu
            align="left"
            side="top"
            triggerClassName={cn("min-w-0", collapsed ? "justify-center" : "w-full")}
            trigger={
              collapsed ? (
                <Avatar name={user?.name ?? user?.email ?? "?"} size="sm" />
              ) : (
                <>
                  <Avatar name={user?.name ?? user?.email ?? "?"} size="sm" />
                  <span className="min-w-0 truncate text-xs text-ink-secondary">{user?.email}</span>
                </>
              )
            }
          >
            <DropdownItem
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              <LogOut className="size-3.5" />
              Log out
            </DropdownItem>
          </DropdownMenu>
          {/* Fixed-size icons, always visible regardless of the row above --
             stacked instead of side-by-side when collapsed, since three
             icons don't fit across the narrow width. */}
          <div className={cn("flex items-center gap-2", collapsed ? "flex-col" : "justify-between")}>
            <NotificationBell />
            <button
              type="button"
              title="Keyboard shortcuts (?)"
              onClick={() => setShortcutsOpen(true)}
              className="shrink-0 rounded-md p-1.5 text-ink-tertiary transition-colors hover:bg-surface-raised hover:text-ink-secondary"
            >
              <Keyboard className="size-4" />
            </button>
            <ThemeToggle />
          </div>
        </div>
      </aside>
      <main className="min-h-0 flex-1 overflow-auto bg-canvas">
        <Outlet />
      </main>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} workspaceId={workspaceId} />
      <KeyboardShortcutsDialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </div>
  );
}
