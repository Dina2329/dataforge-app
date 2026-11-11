export interface User {
  id: string;
  email: string;
  name: string;
}

export interface Notification {
  id: string;
  title: string;
  message: string;
  link: string | null;
  is_read: boolean;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
}

export interface Base {
  id: string;
  workspace_id: string;
  name: string;
  auto_snapshots_enabled: boolean;
}

export interface FieldOption {
  value: string;
  label: string;
  color?: string;
}

export interface ExcludeValuesFrom {
  table_id: string;
  field_id: string;
}

export interface Field {
  id: string;
  table_id: string;
  name: string;
  field_type: string;
  options: {
    choices?: FieldOption[];
    target_table_id?: string;
    link_table_name?: string;
    link_field_id?: string;
    target_field_id?: string;
    aggregate?: RollupAggregate;
    expression?: string;
    // A pointer to one field on one table whose already-used values this
    // field's filter dropdown should suggest fewer of -- never hides rows,
    // only narrows which values the filter's value-picker offers. The target
    // field is not assumed to share this field's name.
    exclude_values_from?: ExcludeValuesFrom;
  } & Record<string, unknown>;
  position: number;
  is_primary: boolean;
  required: boolean;
}

export interface LinkValue {
  row_id: number;
  display: string | null;
}

export interface Attachment {
  id: string;
  filename: string;
  size: number;
  content_type: string;
}

export const ROLLUP_AGGREGATES = ["count", "sum", "avg", "min", "max"] as const;
export type RollupAggregate = (typeof ROLLUP_AGGREGATES)[number];

export const VIEW_TYPES = ["grid", "kanban", "form"] as const;
export type ViewType = (typeof VIEW_TYPES)[number];

export interface ViewSort {
  field: string;
  direction: "asc" | "desc";
}

export interface View {
  id: string;
  table_id: string;
  name: string;
  view_type: ViewType;
  config: {
    group_field_id?: string;
    description?: string;
    field_ids?: string[];
    sort?: ViewSort[];
    filter?: FilterExpr;
    column_order?: string[];
    column_widths?: Record<string, number>;
  } & Record<string, unknown>;
  share_token: string | null;
}

export interface PublicFormField {
  id: string;
  name: string;
  field_type: string;
  options: { choices?: FieldOption[] } & Record<string, unknown>;
  required: boolean;
}

export interface PublicForm {
  table_name: string;
  view_name: string;
  description: string | null;
  fields: PublicFormField[];
}

export interface Table {
  id: string;
  base_id: string;
  name: string;
  fields: Field[];
  views: View[];
}

export interface RecordRow {
  row_id: number;
  version: number;
  created_at: string;
  updated_at: string;
  values: Record<string, unknown>;
}

export interface RecordSubmitConfig {
  id: string;
  table_id: string;
  url: string;
  headers: Record<string, string> | null;
  status_field_id: string | null;
}

export interface BatchSubmitConfig {
  id: string;
  table_id: string;
  url: string;
  headers: Record<string, string> | null;
  // A serialized FilterExpr -- any condition a row can match (not restricted
  // to a single boolean field). {} (no conditions set yet) before the config
  // has ever been saved.
  filter: FilterExpr | Record<string, never>;
  batch_size: number;
}

export interface BatchSubmitPreview {
  matched_count: number;
  batch_size: number;
  total_batches: number;
}

export type BatchSubmitJobStatus = "queued" | "running" | "completed" | "partially_failed" | "failed";

export interface BatchResult {
  batch_index: number;
  row_ids: number[];
  status: "sent" | "failed";
  error?: string;
}

export interface BatchSubmitJob {
  id: string;
  table_id: string;
  status: BatchSubmitJobStatus;
  batch_size: number;
  total_rows: number | null;
  total_batches: number | null;
  sent_batches: number;
  failed_batches: number;
  batch_results: BatchResult[];
  error: string | null;
  dismissed: boolean;
  created_at: string;
  completed_at: string | null;
}

export interface RecordListResponse {
  rows: RecordRow[];
  next_cursor: string | null;
  has_more: boolean;
}

export const FIELD_TYPES = [
  "text",
  "long_text",
  "number",
  "boolean",
  "date",
  "single_select",
  "link_to_record",
  "lookup",
  "rollup",
  "formula",
  "attachment",
] as const;
export type FieldTypeKey = (typeof FIELD_TYPES)[number];

export const SOURCE_TYPES = ["postgres", "mysql", "sqlite", "elasticsearch"] as const;
export type SourceType = (typeof SOURCE_TYPES)[number];

export interface DataSource {
  id: string;
  workspace_id: string;
  name: string;
  source_type: string;
  created_at: string;
}

export interface TableRef {
  name: string;
  schema_name: string | null;
}

export interface ColumnDef {
  name: string;
  native_type: string;
  inferred_field_type: string;
  is_primary_key: boolean;
}

export interface ExcelSheetPreview {
  name: string;
  columns: ColumnDef[];
  row_count: number;
}

export interface ExcelImportResult {
  sheet_name: string;
  table: Table | null;
  error: string | null;
}

export interface TableSyncConfig {
  table_id: string;
  data_source_id: string;
  external_table_name: string;
  sync_enabled: boolean;
  push_requires_approval: boolean;
  consecutive_failures: number;
  last_error: string | null;
  last_error_at: string | null;
  // Stage 2: pulling external changes -- null column means push-only.
  external_updated_at_column: string | null;
  poll_interval_seconds: number | null;
  deletion_check_interval_seconds: number | null;
  last_polled_at: string | null;
  poll_paused: boolean;
  poll_consecutive_failures: number;
  poll_last_error: string | null;
  poll_last_error_at: string | null;
}

// Sync (Stage 1: push DataForge -> source) only supports these -- see
// WRITABLE_SOURCE_TYPES in the backend's connectors/service.py.
export const SYNC_CAPABLE_SOURCE_TYPES = new Set(["postgres", "mysql", "elasticsearch"]);

// One row per (table_id, row_id) an editor has touched on a table gated
// behind push_requires_approval -- "draft" until its editor submits it,
// then "pending" as part of a SyncChangeBatch an owner/admin reviews. See
// PendingSyncChangeService on the backend.
export interface PendingSyncChange {
  id: string;
  table_id: string;
  table_name: string;
  row_id: number;
  operation: "insert" | "update" | "delete";
  values: Record<string, unknown> | null;
  previous_values: Record<string, unknown> | null;
  external_pk: string | null;
  status: "draft" | "pending" | "approved" | "rejected";
  requested_by: string;
  requested_by_name: string;
  requested_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
}

// One "submit for approval" action -- bundles however many PendingSyncChange
// drafts an editor had accumulated, across any number of gated tables, so an
// owner/admin approves/rejects everything in one action.
export interface SyncChangeBatch {
  id: string;
  workspace_id: string;
  status: "pending" | "approved" | "rejected";
  requested_by: string;
  requested_by_name: string;
  submitted_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  changes: PendingSyncChange[];
}

// A point-in-time checkpoint of an entire Base -- see
// app/modules/snapshots on the backend for what "restore" actually does
// (a diff replayed through ordinary record edits, not a raw table swap).
export interface BaseSnapshot {
  id: string;
  base_id: string;
  label: string;
  is_automatic: boolean;
  created_by: string;
  created_at: string;
  table_count: number;
}

export interface SnapshotTableRestoreResult {
  table_name: string;
  skipped: boolean;
  skip_reason: string | null;
  created: number;
  updated: number;
  deleted: number;
  unchanged: number;
  failed: number;
  failures: { row_id: number; error: string }[];
}

export interface RestoreSnapshotResult {
  snapshot_id: string;
  tables: SnapshotTableRestoreResult[];
}

export const FILTER_OPERATORS = [
  "eq",
  "neq",
  "contains",
  "not_contains",
  "gt",
  "gte",
  "lt",
  "lte",
  "is_null",
  "is_not_null",
] as const;
// "in"/"not_in" are deliberately NOT part of FILTER_OPERATORS (the classic
// Filter dialog's operator dropdown) -- that dialog's value input is a
// single scalar, not a checklist, so exposing them there would build a
// broken condition. They're only ever constructed by the column-header
// AutoFilter checklist (see ColumnFilterDropdown.tsx), which needs the wider
// type to type-check its own FilterCondition objects.
export type FilterOperator = (typeof FILTER_OPERATORS)[number] | "in" | "not_in";

export interface FilterCondition {
  kind: "condition";
  field: string;
  operator: FilterOperator;
  value?: unknown;
}

export interface FilterGroup {
  kind: "group";
  logic: "and" | "or";
  items: FilterExpr[];
}

export type FilterExpr = FilterCondition | FilterGroup;

export interface SampleRow {
  row_id: number;
  values: Record<string, unknown>;
}

export interface BulkUpdatePreview {
  matched_count: number;
  sample_rows: SampleRow[];
}

export interface BulkOperation {
  id: string;
  table_id: string;
  status: "pending" | "running" | "completed" | "failed";
  matched_count: number | null;
  affected_count: number | null;
  error: string | null;
  undone_at: string | null;
  created_at: string;
  completed_at: string | null;
}

export const WORKSPACE_ROLES = ["owner", "admin", "editor", "viewer"] as const;
export type WorkspaceRole = (typeof WORKSPACE_ROLES)[number];

export interface PrerequestUpload {
  id: string;
  workspace_id: string;
  original_filename: string;
  row_count: number;
  uploaded_by: string;
  uploaded_at: string;
}

export interface MissingTermsApiConfig {
  id: string;
  workspace_id: string;
  api_url: string;
  headers: Record<string, string> | null;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

export interface MissingTermsConfig {
  id: string;
  table_id: string;
  estate: string | null;
  building: string | null;
  unit: string | null;
  field_mapping: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface MissingTermRow {
  estate: string | null;
  building: string | null;
  unit: string | null;
  sub_domain: string;
  term_name: string;
}

export interface MissingTermsSummary {
  total: number;
  matched: number;
  missing: number;
  in_progress: number;
  ignored: number;
}

export interface IgnoredTermRow {
  sub_domain: string;
  term_name: string;
  created_at: string;
}

export interface MissingTermsListResponse {
  summary: MissingTermsSummary;
  rows: MissingTermRow[];
  next_cursor: string | null;
  has_more: boolean;
}

export type MissingTermsJobStatus = "queued" | "running" | "completed" | "partially_failed" | "failed";

export interface MissingTermsJobSubmitRow {
  sub_domain: string;
  term_name: string;
  estate?: string | null;
  building?: string | null;
  unit?: string | null;
  page?: string | null;
  pdf_image?: string | null;
  pdf_name?: string | null;
  keywords?: string | null;
}

export interface MissingTermsResponseGroup {
  sub_domain: string;
  term_name: string;
  candidates: Record<string, unknown>[];
}

export interface MissingTermsJob {
  id: string;
  table_id: string;
  status: MissingTermsJobStatus;
  submitted_rows: MissingTermsJobSubmitRow[];
  response_rows: MissingTermsResponseGroup[] | null;
  imported_keys: string[] | null;
  error: string | null;
  dismissed: boolean;
  created_at: string;
  completed_at: string | null;
}

export interface ImportSelection {
  sub_domain: string;
  term_name: string;
  candidate_index: number;
  columns: string[];
  overrides?: Record<string, unknown>;
}

export interface ImportResultRow {
  sub_domain: string;
  term_name: string;
  status: "inserted" | "updated" | "skipped";
  row_id: number | null;
}

export interface Member {
  user_id: string;
  email: string;
  name: string;
  role: WorkspaceRole;
}

export interface Team {
  id: string;
  workspace_id: string;
  name: string;
}

export interface TeamMember {
  user_id: string;
  email: string;
  name: string;
}

export const WIDGET_TYPES = ["bar", "line", "pie", "kpi", "table", "pivot"] as const;
export type WidgetTypeKey = (typeof WIDGET_TYPES)[number];

export const AGGREGATES = ["count", "sum", "avg", "min", "max"] as const;
export type Aggregate = (typeof AGGREGATES)[number];

export const DATE_GRANULARITIES = ["day", "week", "month"] as const;
export type DateGranularity = (typeof DATE_GRANULARITIES)[number];

export const WIDGET_SOURCE_TYPES = ["table", "audit_log"] as const;
export type WidgetSourceType = (typeof WIDGET_SOURCE_TYPES)[number];

// Fixed pseudo-columns exposed when a widget's source is the Audit Log
// instead of a real table -- every workspace's audit log has exactly these,
// so there's no per-workspace schema to fetch the way a real table's fields
// are fetched.
export const AUDIT_LOG_FIELDS = ["action", "resource_type", "resource_id", "resource_label", "actor_email", "created_at"] as const;

export interface WidgetPosition {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface WidgetConfig {
  x_field?: string;
  y_field?: string;
  aggregate?: Aggregate;
  filter?: FilterCondition;
  row_field?: string;
  column_field?: string;
  date_granularity?: DateGranularity;
}

export interface Dashboard {
  id: string;
  workspace_id: string;
  name: string;
  share_token: string | null;
  created_at: string;
}

export interface PublicDashboard {
  id: string;
  name: string;
}

export interface Widget {
  id: string;
  dashboard_id: string;
  name: string;
  widget_type: WidgetTypeKey;
  source_type: WidgetSourceType;
  table_id: string | null;
  config: WidgetConfig;
  position: WidgetPosition;
}

export interface PivotData {
  rows: string[];
  columns: string[];
  cells: number[][];
  row_totals: number[];
  column_totals: number[];
  grand_total: number;
}

export interface WidgetData {
  data?: { label: unknown; value: unknown }[] | null;
  value?: unknown;
  rows?: SampleRow[] | null;
  pivot?: PivotData | null;
}

export const TRIGGER_TYPES = ["record_created", "record_updated", "scheduled"] as const;
export type TriggerType = (typeof TRIGGER_TYPES)[number];

export const ACTION_TYPES = ["send_webhook", "create_record", "update_record"] as const;
export type ActionType = (typeof ACTION_TYPES)[number];

export interface AutomationTriggerConfig {
  filter?: FilterCondition;
  cron?: string;
  // record_updated only -- fires only when at least one of these columns was
  // part of the write; absent/empty means "any column."
  watched_fields?: string[];
}

export interface Automation {
  id: string;
  table_id: string;
  name: string;
  trigger_type: TriggerType;
  trigger_config: AutomationTriggerConfig;
  is_enabled: boolean;
  next_run_at: string | null;
  created_at: string;
}

export interface AutomationAction {
  id: string;
  automation_id: string;
  position: number;
  action_type: ActionType;
  config: Record<string, unknown>;
}

export interface AutomationRun {
  id: string;
  automation_id: string;
  status: "success" | "failed";
  trigger_payload: Record<string, unknown>;
  error: string | null;
  ran_at: string;
}

export interface AuditLogEntry {
  id: string;
  workspace_id: string;
  user_id: string | null;
  actor_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  resource_label: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface RowLevelPolicy {
  id: string;
  table_id: string;
  user_id: string;
  filter: FilterCondition;
  created_at: string;
}
