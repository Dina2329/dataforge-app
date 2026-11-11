import { useState } from "react";
import {
  BarChart3,
  GripVertical,
  Hash,
  LayoutDashboard,
  LineChart as LineChartIcon,
  PieChart as PieChartIcon,
  Plus,
  Share2,
  Table2,
  TableProperties,
  X,
} from "lucide-react";
import { useParams } from "react-router-dom";
import GridLayout, { WidthProvider, type Layout } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { useDashboard, useDeleteWidget, useUpdateWidget, useWidgets } from "../hooks/useDashboards";
import { useWorkspaces } from "../hooks/useWorkspaces";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import { AddWidgetDialog } from "../components/dashboard/AddWidgetDialog";
import { ShareDashboardDialog } from "../components/dashboard/ShareDashboardDialog";
import { WidgetRenderer } from "../components/dashboard/WidgetRenderer";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/shared/EmptyState";
import { Breadcrumbs } from "../components/shared/Breadcrumbs";
import { Skeleton } from "../components/ui/Skeleton";
import type { WidgetTypeKey } from "../types";

const ResponsiveGridLayout = WidthProvider(GridLayout);

const WIDGET_ICONS: Record<WidgetTypeKey, typeof BarChart3> = {
  bar: BarChart3,
  line: LineChartIcon,
  pie: PieChartIcon,
  kpi: Hash,
  table: Table2,
  pivot: TableProperties,
};

function BuilderSkeleton() {
  return (
    <div className="grid grid-cols-12 gap-3">
      {[
        "col-span-5 h-40",
        "col-span-4 h-40",
        "col-span-3 h-40",
        "col-span-6 h-56",
        "col-span-6 h-56",
      ].map((cls, i) => (
        <Skeleton key={i} className={cls} />
      ))}
    </div>
  );
}

export function DashboardBuilderPage() {
  const { dashboardId } = useParams<{ dashboardId: string }>();
  const { data: dashboard } = useDashboard(dashboardId);
  useReportWorkspaceContext(dashboard?.workspace_id);
  const { data: workspaces } = useWorkspaces();
  const workspaceName = workspaces?.find((w) => w.id === dashboard?.workspace_id)?.name;
  const { data: widgets } = useWidgets(dashboardId);
  const updateWidget = useUpdateWidget(dashboardId);
  const deleteWidget = useDeleteWidget(dashboardId);
  const [addWidgetOpen, setAddWidgetOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);

  function handleLayoutChange(_layout: Layout[], oldItem: Layout, newItem: Layout) {
    if (oldItem.x === newItem.x && oldItem.y === newItem.y && oldItem.w === newItem.w && oldItem.h === newItem.h) return;
    updateWidget.mutate({ widgetId: newItem.i, position: { x: newItem.x, y: newItem.y, w: newItem.w, h: newItem.h } });
  }

  if (!dashboard || !widgets) {
    return (
      <div className="flex h-full flex-col p-6">
        <Skeleton className="mb-2 h-3 w-40" />
        <div className="mb-4 flex items-center justify-between">
          <Skeleton className="h-7 w-56" />
          <div className="flex gap-2">
            <Skeleton className="h-9 w-24" />
            <Skeleton className="h-9 w-24" />
          </div>
        </div>
        <BuilderSkeleton />
      </div>
    );
  }

  const layout: Layout[] = widgets.map((w) => ({ i: w.id, x: w.position.x, y: w.position.y, w: w.position.w, h: w.position.h }));

  return (
    <div className="flex h-full flex-col p-6">
      {workspaceName && (
        <div className="mb-2">
          <Breadcrumbs
            items={[{ label: workspaceName, to: "/" }, { label: "Dashboards", to: `/workspaces/${dashboard.workspace_id}/dashboards` }, { label: dashboard.name }]}
          />
        </div>
      )}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent-secondary-tint">
            <LayoutDashboard className="size-4 text-accent-secondary" />
          </div>
          <h1 className="text-xl font-semibold text-ink-primary">{dashboard.name}</h1>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setShareOpen(true)}>
            <Share2 className="size-4" /> Share
          </Button>
          <Button onClick={() => setAddWidgetOpen(true)}>
            <Plus className="size-4" /> Widget
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {widgets.length === 0 ? (
          <EmptyState
            icon={LayoutDashboard}
            title="No widgets yet"
            description="Add one to start visualizing your data."
            action={
              <Button onClick={() => setAddWidgetOpen(true)}>
                <Plus className="size-4" /> Add widget
              </Button>
            }
          />
        ) : (
          <ResponsiveGridLayout
            layout={layout}
            cols={12}
            rowHeight={60}
            margin={[12, 12]}
            containerPadding={[0, 0]}
            onDragStop={handleLayoutChange}
            onResizeStop={handleLayoutChange}
            draggableCancel=".widget-no-drag"
          >
            {widgets.map((widget) => {
              const Icon = WIDGET_ICONS[widget.widget_type];
              return (
                <div
                  key={widget.id}
                  className="group overflow-hidden rounded-xl border border-border-default bg-surface transition-shadow hover:shadow-sm"
                >
                  <div className="flex h-8 shrink-0 cursor-grab items-center justify-between border-b border-border-default bg-surface-raised px-2.5 active:cursor-grabbing">
                    <span className="flex min-w-0 items-center gap-1.5 text-xs font-medium text-ink-secondary">
                      <GripVertical className="size-3 shrink-0 text-ink-tertiary" />
                      <Icon className="size-3 shrink-0 text-accent-secondary" />
                      <span className="truncate">{widget.name}</span>
                    </span>
                    <button
                      className="widget-no-drag shrink-0 rounded p-0.5 text-ink-tertiary opacity-0 transition-opacity hover:bg-status-danger-tint hover:text-status-danger group-hover:opacity-100"
                      onClick={() => deleteWidget.mutate(widget.id)}
                    >
                      <X className="size-3.5" />
                    </button>
                  </div>
                  <div style={{ height: "calc(100% - 32px)" }}>
                    <WidgetRenderer widget={widget} dashboardId={dashboardId!} />
                  </div>
                </div>
              );
            })}
          </ResponsiveGridLayout>
        )}
      </div>

      {dashboardId && (
        <AddWidgetDialog
          workspaceId={dashboard.workspace_id}
          dashboardId={dashboardId}
          existingWidgets={widgets}
          open={addWidgetOpen}
          onClose={() => setAddWidgetOpen(false)}
        />
      )}
      {dashboardId && (
        <ShareDashboardDialog
          dashboardId={dashboardId}
          shareToken={dashboard.share_token}
          open={shareOpen}
          onClose={() => setShareOpen(false)}
        />
      )}
    </div>
  );
}
