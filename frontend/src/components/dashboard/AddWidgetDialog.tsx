import { useState } from "react";
import { BarChart3 } from "lucide-react";
import {
  AGGREGATES,
  AUDIT_LOG_FIELDS,
  DATE_GRANULARITIES,
  WIDGET_SOURCE_TYPES,
  WIDGET_TYPES,
  type Aggregate,
  type DateGranularity,
  type Widget,
  type WidgetConfig,
  type WidgetSourceType,
  type WidgetTypeKey,
} from "../../types";
import { useCreateWidget, usePreviewWidgetData, useWorkspaceTables } from "../../hooks/useDashboards";
import { useTable } from "../../hooks/useBases";
import { apiErrorMessage } from "../../lib/apiClient";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { FormField } from "../ui/FormField";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";
import { WidgetVisual } from "./WidgetRenderer";

const WIDGET_TYPE_LABELS: Record<WidgetTypeKey, string> = {
  bar: "Bar chart",
  line: "Line chart",
  pie: "Pie chart",
  kpi: "KPI number",
  table: "Table",
  pivot: "Pivot table",
};

const SOURCE_TYPE_LABELS: Record<WidgetSourceType, string> = {
  table: "Table",
  audit_log: "Audit log",
};

// A plain {id, name, field_type} shape covers both: a real table's own
// fields, and the Audit Log's fixed pseudo-columns -- letting every picker
// below (Group by / Rows / Columns / Aggregate field) render identically
// regardless of which source is selected, no branching per-field-list.
interface PickableField {
  id: string;
  name: string;
  field_type: string;
}

const AUDIT_LOG_PICKABLE_FIELDS: PickableField[] = AUDIT_LOG_FIELDS.map((name) => ({
  id: name,
  name,
  field_type: name === "created_at" ? "date" : "text",
}));

interface AddWidgetDialogProps {
  workspaceId: string;
  dashboardId: string;
  existingWidgets: Widget[];
  open: boolean;
  onClose: () => void;
}

export function AddWidgetDialog({ workspaceId, dashboardId, existingWidgets, open, onClose }: AddWidgetDialogProps) {
  // Gated on open -- this dialog is always mounted on the dashboard builder
  // page, and useWorkspaceTables fans out one request per base plus one per
  // table in the whole workspace (see its own docstring), not something that
  // should fire on every page load just because the dialog could be opened.
  const { data: tables } = useWorkspaceTables(open ? workspaceId : undefined);
  const createWidget = useCreateWidget(dashboardId);

  const [name, setName] = useState("");
  const [widgetType, setWidgetType] = useState<WidgetTypeKey>("bar");
  const [sourceType, setSourceType] = useState<WidgetSourceType>("table");
  const [tableId, setTableId] = useState("");
  const [xField, setXField] = useState("");
  const [yField, setYField] = useState("");
  const [aggregate, setAggregate] = useState<Aggregate>("count");
  const [rowField, setRowField] = useState("");
  const [columnField, setColumnField] = useState("");
  const [dateGranularity, setDateGranularity] = useState<DateGranularity>("day");
  // Audit-log-only: scope the widget down to one table's activity. Not
  // every audit action has a table at all (dashboard.*, base.*, member.*),
  // so this stays a plain equality filter on the "table_id" pseudo-column,
  // never one of the Group by/Rows/Columns fields (a raw table UUID makes a
  // useless axis label).
  const [auditTableId, setAuditTableId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isAuditLog = sourceType === "audit_log";
  const { data: selectedTable } = useTable(!isAuditLog && tableId ? tableId : undefined);
  const fields: PickableField[] = isAuditLog ? AUDIT_LOG_PICKABLE_FIELDS : (selectedTable?.fields ?? []);

  const isPivot = widgetType === "pivot";
  const needsXField = widgetType === "bar" || widgetType === "line" || widgetType === "pie";
  const needsYField = aggregate !== "count" && widgetType !== "table";
  const columnFieldIsDate = fields.find((f) => f.name === columnField)?.field_type === "date";

  const previewConfig: WidgetConfig = {
    ...(needsXField ? { x_field: xField } : {}),
    ...(isPivot ? { row_field: rowField, column_field: columnField } : {}),
    ...(isPivot && columnFieldIsDate ? { date_granularity: dateGranularity } : {}),
    ...(widgetType !== "table" ? { aggregate } : {}),
    ...(needsYField ? { y_field: yField } : {}),
    ...(isAuditLog && auditTableId ? { filter: { kind: "condition", field: "table_id", operator: "eq", value: auditTableId } } : {}),
  };
  const previewReady =
    (isAuditLog || !!tableId) &&
    (!needsXField || !!xField) &&
    (!needsYField || !!yField) &&
    (!isPivot || (!!rowField && !!columnField));
  const preview = usePreviewWidgetData({
    sourceType,
    tableId: isAuditLog ? undefined : tableId,
    workspaceId: isAuditLog ? workspaceId : undefined,
    widgetType,
    config: previewConfig,
    enabled: previewReady,
  });

  function reset() {
    setName("");
    setSourceType("table");
    setTableId("");
    setXField("");
    setYField("");
    setAggregate("count");
    setRowField("");
    setColumnField("");
    setDateGranularity("day");
    setAuditTableId("");
    setError(null);
  }

  async function handleCreate() {
    if (!name.trim() || (!isAuditLog && !tableId)) {
      setError(`Give the widget a name${isAuditLog ? "" : " and pick a table"}`);
      return;
    }
    if (needsXField && !xField) {
      setError("Pick a field to group by");
      return;
    }
    if (isPivot && (!rowField || !columnField)) {
      setError("Pick a field for rows and a field for columns");
      return;
    }
    if (needsYField && !yField) {
      setError("Pick a field to aggregate");
      return;
    }
    setError(null);
    // Place the new widget below everything else — react-grid-layout's own
    // "Infinity" bottom-placement convention doesn't survive a JSON round
    // trip (JSON.stringify turns Infinity into null), so compute a real y.
    const nextY = existingWidgets.reduce((max, w) => Math.max(max, w.position.y + w.position.h), 0);
    try {
      await createWidget.mutateAsync({
        name: name.trim(),
        widget_type: widgetType,
        source_type: sourceType,
        table_id: isAuditLog ? null : tableId,
        config: previewConfig,
        position: { x: 0, y: nextY, w: 4, h: 4 },
      });
      reset();
      onClose();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not create widget"));
    }
  }

  return (
    <Dialog
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="Add widget"
      size="lg"
    >
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div className="flex flex-col gap-3">
          <FormField label="Widget name">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Tasks by status" />
          </FormField>

          <FormField label="Type">
            <Select value={widgetType} onChange={(e) => setWidgetType(e.target.value as WidgetTypeKey)}>
              {WIDGET_TYPES.map((type) => (
                <option key={type} value={type}>
                  {WIDGET_TYPE_LABELS[type]}
                </option>
              ))}
            </Select>
          </FormField>

          <FormField label="Data source">
            <Select
              value={sourceType}
              onChange={(e) => {
                setSourceType(e.target.value as WidgetSourceType);
                setTableId("");
                setXField("");
                setYField("");
                setRowField("");
                setColumnField("");
                setAuditTableId("");
              }}
            >
              {WIDGET_SOURCE_TYPES.map((st) => (
                <option key={st} value={st}>
                  {SOURCE_TYPE_LABELS[st]}
                </option>
              ))}
            </Select>
          </FormField>

          {isAuditLog && (
            <FormField label="Filter by table (optional)">
              <Select value={auditTableId} onChange={(e) => setAuditTableId(e.target.value)}>
                <option value="">All tables</option>
                {tables?.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </FormField>
          )}

          {!isAuditLog && (
            <FormField label="Table">
              <Select
                value={tableId}
                onChange={(e) => {
                  setTableId(e.target.value);
                  setXField("");
                  setYField("");
                  setRowField("");
                  setColumnField("");
                }}
              >
                <option value="">Select a table…</option>
                {tables?.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </FormField>
          )}

          {needsXField && (
            <FormField label="Group by">
              <Select value={xField} onChange={(e) => setXField(e.target.value)}>
                <option value="">Select a field…</option>
                {fields.map((f) => (
                  <option key={f.id} value={f.name}>
                    {f.name}
                  </option>
                ))}
              </Select>
            </FormField>
          )}

          {isPivot && (
            <>
              <div className="flex gap-2">
                <div className="flex-1">
                  <FormField label="Rows">
                    <Select value={rowField} onChange={(e) => setRowField(e.target.value)}>
                      <option value="">Select a field…</option>
                      {fields.map((f) => (
                        <option key={f.id} value={f.name}>
                          {f.name}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                </div>
                <div className="flex-1">
                  <FormField label="Columns">
                    <Select value={columnField} onChange={(e) => setColumnField(e.target.value)}>
                      <option value="">Select a field…</option>
                      {fields.map((f) => (
                        <option key={f.id} value={f.name}>
                          {f.name}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                </div>
              </div>
              {columnFieldIsDate && (
                <FormField label="Bucket columns by">
                  <Select value={dateGranularity} onChange={(e) => setDateGranularity(e.target.value as DateGranularity)}>
                    {DATE_GRANULARITIES.map((g) => (
                      <option key={g} value={g}>
                        {g}
                      </option>
                    ))}
                  </Select>
                </FormField>
              )}
            </>
          )}

          {widgetType !== "table" && (
            <div className="flex gap-2">
              <div className="flex-1">
                <FormField label="Aggregate">
                  <Select value={aggregate} onChange={(e) => setAggregate(e.target.value as Aggregate)}>
                    {AGGREGATES.map((agg) => (
                      <option key={agg} value={agg}>
                        {agg}
                      </option>
                    ))}
                  </Select>
                </FormField>
              </div>
              {needsYField && (
                <div className="flex-1">
                  <FormField label="Field">
                    <Select value={yField} onChange={(e) => setYField(e.target.value)}>
                      <option value="">Select a field…</option>
                      {fields.map((f) => (
                        <option key={f.id} value={f.name}>
                          {f.name}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                </div>
              )}
            </div>
          )}

          {error && <p className="text-sm text-status-danger">{error}</p>}

          <Button onClick={handleCreate} loading={createWidget.isPending} className="mt-1 w-full">
            Add widget
          </Button>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-ink-secondary">Preview</span>
          <div className="flex h-56 items-center justify-center rounded-lg border border-border-default bg-surface-raised">
            {!previewReady ? (
              <div className="flex flex-col items-center gap-2 text-center text-xs text-ink-tertiary">
                <BarChart3 className="size-6" />
                <span>
                  Pick{isAuditLog ? "" : " a table"}
                  {needsXField || isPivot ? " and a field" : ""} to see a preview
                </span>
              </div>
            ) : preview.isLoading ? (
              <span className="text-xs text-ink-tertiary">Loading preview…</span>
            ) : preview.error ? (
              <span className="px-4 text-center text-xs text-status-danger">Could not load a preview for this config</span>
            ) : preview.data ? (
              <div className="size-full p-2">
                <WidgetVisual widgetType={widgetType} data={preview.data} />
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </Dialog>
  );
}
