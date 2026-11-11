import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useNavigate } from "react-router-dom";
import type { Widget, WidgetData, WidgetTypeKey } from "../../types";
import { usePublicWidgetData, useWidgetData } from "../../hooks/useDashboards";
import { useCountUp } from "../../hooks/useCountUp";

// Fixed-order categorical palette (dataviz skill reference palette) -- never cycle/reorder per series.
const CATEGORICAL_COLORS = [
  "#2a78d6", // blue
  "#1baf7a", // aqua
  "#eda100", // yellow
  "#008300", // green
  "#4a3aa7", // violet
  "#e34948", // red
  "#e87ba4", // magenta
  "#eb6834", // orange
];
const SERIES_COLOR = CATEGORICAL_COLORS[0];
// CSS custom properties (defined in index.css, flipped by the `.dark` class)
// rather than hardcoded hex -- SVG presentation attributes resolve var() same
// as any other CSS value, so these charts follow the theme with no JS branch.
const GRIDLINE = "var(--chart-gridline)";
const AXIS_INK = "var(--chart-axis-ink)";
const CHART_SURFACE = "var(--chart-surface)";
const SECONDARY_INK = "var(--chart-secondary-ink)";

const chartTickStyle = { fontSize: 11, fill: AXIS_INK };

// Series-count ladder (dataviz skill, choosing-a-form.md): past ~7-8 bins,
// adjacent categorical bars/slices blur together and the x-axis labels
// collide -- fold the long tail into "Other" rather than rendering every
// distinct value the underlying query happens to group by (a high-cardinality
// group-by field, e.g. an email domain, can otherwise produce dozens of
// slivers no reader can parse).
const MAX_CATEGORIES = 8;

function foldTailIntoOther(data: { label: string; value: number }[]): { label: string; value: number }[] {
  const sorted = [...data].sort((a, b) => b.value - a.value);
  if (sorted.length <= MAX_CATEGORIES) return sorted;
  const head = sorted.slice(0, MAX_CATEGORIES - 1);
  const tailTotal = sorted.slice(MAX_CATEGORIES - 1).reduce((sum, d) => sum + d.value, 0);
  return [...head, { label: "Other", value: tailTotal }];
}

const MAX_LABEL_CHARS = 10;

function truncateLabel(label: string): string {
  return label.length > MAX_LABEL_CHARS ? `${label.slice(0, MAX_LABEL_CHARS - 1)}…` : label;
}

function formatKpiValue(value: unknown): string {
  if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return String(value ?? "—");
}

// A hero/stat-tile figure reads better with proportional digits, not a
// monospace/tabular-nums face (dataviz skill anti-patterns: equal-width
// digits make a large standalone number look loose) -- tabular-nums stays
// reserved for numbers that need to align vertically (table rows, axis ticks).
function KpiValue({ value }: { value: unknown }) {
  const numeric = typeof value === "number" ? value : null;
  const animated = useCountUp(numeric);
  const display = numeric !== null ? formatKpiValue(animated) : formatKpiValue(value);
  return (
    <div className="flex h-full items-center justify-center">
      <span className="text-4xl font-semibold text-ink-primary">{display}</span>
    </div>
  );
}

/** Pure presentational chart/kpi/table rendering, given already-fetched data
 * -- shared by WidgetRenderer (fetches a real, saved widget's data) and the
 * Add Widget dialog's live preview (fetches unsaved config against
 * /widgets/preview), so both stay pixel-identical without duplicating the
 * chart-type branching. */
export function WidgetVisual({
  widgetType,
  data,
  onSegmentClick,
}: {
  widgetType: WidgetTypeKey;
  data: WidgetData;
  /** Bar/pie only -- clicking a segment hands back its label so the caller
   * can drill into the underlying rows. Omitted (no cursor, no handler)
   * anywhere drilling down doesn't make sense, e.g. the Add Widget preview. */
  onSegmentClick?: (label: string) => void;
}) {
  if (widgetType === "kpi") {
    return <KpiValue value={data.value} />;
  }

  if (widgetType === "pivot") {
    const pivot = data.pivot;
    if (!pivot || pivot.rows.length === 0) {
      return <p className="flex h-full items-center justify-center text-xs text-ink-tertiary">No data</p>;
    }
    return (
      <div className="h-full overflow-auto p-2">
        <table className="w-full border-collapse text-left text-xs tabular-nums">
          <thead>
            <tr className="text-ink-tertiary">
              <th className="sticky left-0 bg-surface px-2 py-1 font-medium" />
              {pivot.columns.map((col) => (
                <th key={col} className="whitespace-nowrap px-2 py-1 text-right font-medium">
                  {col}
                </th>
              ))}
              <th className="whitespace-nowrap px-2 py-1 text-right font-semibold text-ink-secondary">Total</th>
            </tr>
          </thead>
          <tbody>
            {pivot.rows.map((row, i) => (
              <tr key={row} className="border-t border-border-default">
                <td className="sticky left-0 bg-surface px-2 py-1 font-medium text-ink-primary">{row}</td>
                {pivot.cells[i].map((value, j) => (
                  <td key={pivot.columns[j]} className="px-2 py-1 text-right text-ink-secondary">
                    {value}
                  </td>
                ))}
                <td className="px-2 py-1 text-right font-semibold text-ink-primary">{pivot.row_totals[i]}</td>
              </tr>
            ))}
            <tr className="border-t-2 border-border-strong">
              <td className="sticky left-0 bg-surface px-2 py-1 font-semibold text-ink-primary">Total</td>
              {pivot.column_totals.map((value, j) => (
                <td key={pivot.columns[j]} className="px-2 py-1 text-right font-semibold text-ink-primary">
                  {value}
                </td>
              ))}
              <td className="px-2 py-1 text-right font-semibold text-ink-primary">{pivot.grand_total}</td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

  if (widgetType === "table") {
    const rows = data.rows ?? [];
    const columns = rows.length > 0 ? Object.keys(rows[0].values) : [];
    return (
      <div className="h-full overflow-auto p-2">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-ink-tertiary">
              {columns.map((col) => (
                <th key={col} className="px-2 py-1 font-medium">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.row_id} className="border-t border-border-default">
                {columns.map((col) => (
                  <td key={col} className="px-2 py-1 text-ink-secondary">
                    {String(row.values[col] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  const rawChartData = (data.data ?? []).map((d) => ({ label: String(d.label ?? "—"), value: Number(d.value ?? 0) }));
  // Bar/pie are magnitude/part-to-whole comparisons -- sorting descending and
  // folding the tail applies to both; line is a trend/ordered axis, so it's
  // left in its natural (already server-sorted-by-group-key) order.
  const chartData = widgetType === "line" ? rawChartData : foldTailIntoOther(rawChartData);

  if (widgetType === "pie") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={chartData}
            dataKey="value"
            nameKey="label"
            cx="50%"
            cy="50%"
            outerRadius="65%"
            paddingAngle={2}
            stroke={CHART_SURFACE}
            strokeWidth={2}
          >
            {chartData.map((entry, i) => (
              <Cell
                key={i}
                fill={CATEGORICAL_COLORS[i % CATEGORICAL_COLORS.length]}
                cursor={onSegmentClick ? "pointer" : undefined}
                onClick={onSegmentClick && entry.label !== "Other" ? () => onSegmentClick(entry.label) : undefined}
              />
            ))}
          </Pie>
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: GRIDLINE, background: CHART_SURFACE }} />
          <Legend
            verticalAlign="bottom"
            height={28}
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 11, color: SECONDARY_INK }}
          />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  if (widgetType === "line") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRIDLINE} vertical={false} />
          <XAxis dataKey="label" tick={chartTickStyle} axisLine={{ stroke: GRIDLINE }} tickLine={false} />
          <YAxis tick={chartTickStyle} axisLine={false} tickLine={false} width={36} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: GRIDLINE, background: CHART_SURFACE }} cursor={{ stroke: GRIDLINE }} />
          <Line
            type="monotone"
            dataKey="value"
            stroke={SERIES_COLOR}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: SERIES_COLOR }}
          />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} margin={{ top: 8, right: 12, left: -8, bottom: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRIDLINE} vertical={false} />
        <XAxis
          dataKey="label"
          tickFormatter={truncateLabel}
          tick={{ ...chartTickStyle, angle: -35, textAnchor: "end" }}
          height={46}
          axisLine={{ stroke: GRIDLINE }}
          tickLine={false}
          interval={0}
        />
        <YAxis tick={chartTickStyle} axisLine={false} tickLine={false} width={36} />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: GRIDLINE, background: CHART_SURFACE }}
          cursor={{ fill: SERIES_COLOR, fillOpacity: 0.06 }}
        />
        <Bar dataKey="value" fill={SERIES_COLOR} radius={[4, 4, 0, 0]} maxBarSize={48}>
          {onSegmentClick &&
            chartData.map((entry, i) => (
              <Cell
                key={i}
                fill={SERIES_COLOR}
                cursor="pointer"
                onClick={() => entry.label !== "Other" && onSegmentClick(entry.label)}
              />
            ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

interface WidgetRendererProps {
  widget: Pick<Widget, "widget_type" | "id" | "table_id" | "config">;
  dashboardId?: string;
  shareToken?: string;
}

export function WidgetRenderer({ widget, dashboardId, shareToken }: WidgetRendererProps) {
  const navigate = useNavigate();
  const privateQuery = useWidgetData(shareToken ? undefined : dashboardId, widget.id);
  const publicQuery = usePublicWidgetData(shareToken, widget.id);
  const { data, isLoading, error } = shareToken ? publicQuery : privateQuery;

  if (isLoading) return <p className="p-4 text-xs text-ink-tertiary">Loading…</p>;
  if (error) return <p className="p-4 text-xs text-status-danger">Could not load data</p>;
  if (!data) return null;

  // A public/shared dashboard has no authenticated session to drill into --
  // the table view it would land on requires login, so the click is simply
  // not offered there (no dead-end navigation for an anonymous viewer). An
  // audit_log-sourced widget has no table_id to drill into at all.
  const xField = widget.config.x_field;
  const onSegmentClick =
    !shareToken && xField && widget.table_id
      ? (label: string) => {
          const params = new URLSearchParams({ filterField: xField, filterValue: label });
          navigate(`/tables/${widget.table_id}?${params.toString()}`);
        }
      : undefined;

  return <WidgetVisual widgetType={widget.widget_type} data={data} onSegmentClick={onSegmentClick} />;
}
