import type { Field, FilterCondition, FilterExpr, FilterOperator } from "../types";

// Types a filter condition can't meaningfully target -- not real stored
// values (link_to_record/lookup/rollup/formula are computed, attachment has
// no comparable scalar). Shared by any UI that lets a person build a filter
// by hand (GridFilterDialog, Batch Submit's config dialog).
export const NON_FILTERABLE_TYPES = new Set(["link_to_record", "lookup", "rollup", "formula", "attachment"]);

export const OPERATOR_LABELS: Record<FilterOperator, string> = {
  eq: "equals",
  neq: "does not equal",
  contains: "contains",
  not_contains: "does not contain",
  gt: "greater than",
  gte: "greater than or equal",
  lt: "less than",
  lte: "less than or equal",
  is_null: "is empty",
  is_not_null: "is not empty",
  // Set only by the column-header AutoFilter checklist -- see FilterOperator's
  // own comment in types/index.ts for why these aren't in FILTER_OPERATORS.
  in: "is any of",
  not_in: "is none of",
};

export const NO_VALUE_OPERATORS = new Set<FilterOperator>(["is_null", "is_not_null"]);

export function coerceForField(field: Field | undefined, raw: string): unknown {
  if (!field) return raw;
  if (field.field_type === "number") return raw === "" ? null : Number(raw);
  if (field.field_type === "boolean") return raw === "true";
  return raw;
}

// A view's filter is one FilterExpr tree shared by both the classic Filter
// dialog (GridFilterDialog) and the column-header AutoFilter checklist
// (ColumnFilterDropdown) -- these read/write exactly one field's condition
// within it without disturbing whatever the other UI has set for every other
// field, using the same flatten convention GridFilterDialog's own
// toRows/handleApply already use (0 conditions -> undefined, 1 -> a bare
// condition, 2+ -> an AND group) so edits from either surface stay
// interoperable instead of silently clobbering each other.
export function flatConditions(filter: FilterExpr | undefined): FilterCondition[] {
  if (!filter) return [];
  if (filter.kind === "condition") return [filter];
  return filter.items.filter((i): i is FilterCondition => i.kind === "condition");
}

/** The AutoFilter checklist's own "in" condition for one field, or null if
 * that field currently has no AutoFilter selection applied. */
export function getColumnFilterValues(filter: FilterExpr | undefined, fieldName: string): unknown[] | null {
  const match = flatConditions(filter).find((c) => c.field === fieldName && c.operator === "in");
  return match && Array.isArray(match.value) ? match.value : null;
}

/** Replaces (or clears, if `values` is null) one field's AutoFilter "in"
 * condition, leaving every other field's condition -- AutoFilter-set or
 * otherwise -- untouched. */
export function setColumnFilterValues(filter: FilterExpr | undefined, fieldName: string, values: unknown[] | null): FilterExpr | undefined {
  const otherConditions = flatConditions(filter).filter((c) => c.field !== fieldName);
  const nextConditions: FilterCondition[] =
    values === null ? otherConditions : [...otherConditions, { kind: "condition", field: fieldName, operator: "in", value: values }];
  if (nextConditions.length === 0) return undefined;
  if (nextConditions.length === 1) return nextConditions[0];
  return { kind: "group", logic: "and", items: nextConditions };
}

/** Every OTHER field's condition, with this one stripped out -- what the
 * AutoFilter checklist sends the server as `other_filter` so a second
 * column's value list only offers what's actually left once the first
 * column's filter has already narrowed things down (Excel's own AutoFilter
 * cascades the same way). Re-including this field's own condition would be
 * a no-op at best (it's about to be replaced) and self-contradictory at
 * worst (checking against its own not-yet-applied selection). */
export function filterExcludingField(filter: FilterExpr | undefined, fieldName: string): FilterExpr | undefined {
  const otherConditions = flatConditions(filter).filter((c) => c.field !== fieldName);
  if (otherConditions.length === 0) return undefined;
  if (otherConditions.length === 1) return otherConditions[0];
  return { kind: "group", logic: "and", items: otherConditions };
}

// -- Shared editable-rows <-> FilterExpr conversion, for any UI that lets a
// person build an arbitrary multi-condition (AND) filter by hand -- the
// classic Filter dialog (GridFilterDialog) and Batch Submit's "which rows
// are ready to send" condition both need exactly this, just bound to a
// different field's data afterward.

export interface FilterRow {
  key: number;
  field: string;
  operator: FilterOperator;
  valueRaw: string;
}

let nextFilterRowKey = 1;

export function emptyFilterRow(field: string): FilterRow {
  return { key: nextFilterRowKey++, field, operator: "eq", valueRaw: "" };
}

/** A FilterExpr tree -> editable rows, keeping only plain conditions (a
 * nested group isn't representable by this flat row-list editor, same
 * limitation GridFilterDialog already had). */
export function filterExprToRows(filter: FilterExpr | undefined): FilterRow[] {
  return flatConditions(filter).map((c) => ({
    key: nextFilterRowKey++,
    field: c.field,
    operator: c.operator,
    valueRaw: c.value == null ? "" : String(c.value),
  }));
}

/** The inverse -- editable rows -> a FilterExpr tree, with the field list so
 * each row's raw text value is coerced to that field's real type (number,
 * boolean, ...) before being sent to the server. 0 rows -> undefined (no
 * filter at all), 1 -> a bare condition, 2+ -> an AND group. */
export function rowsToFilterExpr(rows: FilterRow[], fields: Field[]): FilterExpr | undefined {
  const conditions: FilterCondition[] = rows.map((row) => {
    const field = fields.find((f) => f.name === row.field);
    return {
      kind: "condition",
      field: row.field,
      operator: row.operator,
      value: NO_VALUE_OPERATORS.has(row.operator) ? undefined : coerceForField(field, row.valueRaw),
    };
  });
  if (conditions.length === 0) return undefined;
  if (conditions.length === 1) return conditions[0];
  return { kind: "group", logic: "and", items: conditions };
}
