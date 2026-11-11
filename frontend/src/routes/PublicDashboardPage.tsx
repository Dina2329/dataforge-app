import { LayoutDashboard } from "lucide-react";
import { useParams } from "react-router-dom";
import { usePublicDashboard, usePublicWidgets } from "../hooks/useDashboards";
import { WidgetRenderer } from "../components/dashboard/WidgetRenderer";
import { EmptyState } from "../components/shared/EmptyState";
import { PageSpinner } from "../components/shared/PageSpinner";

export function PublicDashboardPage() {
  const { token } = useParams<{ token: string }>();
  const { data: dashboard, isLoading: dashboardLoading, isError } = usePublicDashboard(token);
  const { data: widgets } = usePublicWidgets(token);

  if (isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas p-8">
        <EmptyState icon={LayoutDashboard} title="Link not found" description="This share link is invalid or has been revoked." />
      </div>
    );
  }

  if (dashboardLoading || !dashboard || !widgets) {
    return (
      <div className="min-h-screen bg-canvas">
        <PageSpinner />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-canvas">
      <div className="border-b border-border-default bg-surface px-8 py-4">
        <div className="mx-auto flex max-w-6xl items-center gap-2.5">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent-secondary-tint">
            <LayoutDashboard className="size-4 text-accent-secondary" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-ink-primary">{dashboard.name}</h1>
            <p className="text-xs text-ink-tertiary">Shared read-only view · DataForge</p>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl p-8">
        {widgets.length === 0 ? (
          <EmptyState icon={LayoutDashboard} title="No widgets" description="This dashboard doesn't have any widgets yet." />
        ) : (
          <div className="grid grid-cols-12 gap-4">
            {widgets.map((widget) => (
              <div
                key={widget.id}
                className="overflow-hidden rounded-xl border border-border-default bg-surface"
                style={{ gridColumn: `span ${widget.position.w} / span ${widget.position.w}`, height: widget.position.h * 60 }}
              >
                <div className="border-b border-border-default bg-surface-raised px-2.5 py-1.5">
                  <span className="text-xs font-medium text-ink-secondary">{widget.name}</span>
                </div>
                <div style={{ height: "calc(100% - 32px)" }}>
                  <WidgetRenderer widget={widget} shareToken={token} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
