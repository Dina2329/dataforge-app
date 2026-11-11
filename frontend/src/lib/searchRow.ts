import type { Field, RecordRow } from "../types";

function cellToText(value: unknown): string {
  if (value == null) return "";
  if (Array.isArray(value)) {
    return value
      .map((item) => (item && typeof item === "object" ? String((item as Record<string, unknown>).display ?? (item as Record<string, unknown>).filename ?? "") : String(item)))
      .join(" ");
  }
  return String(value);
}

/** Client-side quick search over the rows already loaded in the grid --
 * matches if any field's value contains the query, case-insensitive. This is
 * separate from GridFilterDialog's server-side saved filter: it's ephemeral,
 * resets on navigation, and only searches what's already on screen. */
export function rowMatchesSearch(row: RecordRow, fields: Field[], query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return fields.some((field) => cellToText(row.values[field.name]).toLowerCase().includes(needle));
}
