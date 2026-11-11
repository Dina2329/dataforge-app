import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Filter, Search } from "lucide-react";
import { apiClient } from "../../lib/apiClient";
import { cn } from "../../lib/cn";
import type { Field, FilterExpr } from "../../types";
import { Input } from "../ui/Input";

interface ColumnFilterDropdownProps {
  field: Field;
  /** This field's current AutoFilter selection (see
   * filterHelpers.getColumnFilterValues), or null if none is applied -- null
   * also means "everything is checked" the next time the dropdown opens,
   * matching Excel's own default. */
  currentValues: unknown[] | null;
  /** Every OTHER column's currently-active filter (see
   * filterHelpers.filterExcludingField) -- the value list this field offers
   * is scoped to rows matching these, the same cascading behavior Excel's
   * own AutoFilter has: once Status is filtered to "todo", Owner's checklist
   * only offers owners of todo rows, not everyone in the table. */
  otherFilters: FilterExpr | undefined;
  /** null clears this field's condition entirely (the "Select all" case) --
   * kept distinct from an empty array, which means "show nothing" (every
   * box unchecked), same as Excel's own AutoFilter. */
  onApply: (values: unknown[] | null) => void;
}

const BOOLEAN_LABELS: Record<string, string> = { true: "Checked", false: "Unchecked" };

/** Excel/Sheets-style AutoFilter: click the funnel, get a checklist of this
 * column's own distinct values, check/uncheck, Apply. Deliberately NOT built
 * on DropdownMenu -- that component closes on any click inside its panel
 * (fine for a menu of one-shot actions, wrong for a checklist that needs to
 * stay open across many toggles), so this owns its own open state, outside-
 * click dismissal, and scroll dismissal, the same mechanics minus the
 * close-on-inner-click behavior. */
export function ColumnFilterDropdown({ field, currentValues, otherFilters, onApply }: ColumnFilterDropdownProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const rootRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);

  const isBoolean = field.field_type === "boolean";
  const isSingleSelect = field.field_type === "single_select";
  const otherFiltersKey = otherFilters ? JSON.stringify(otherFilters) : undefined;

  // Always fetched, even for boolean/single_select -- their full domain is
  // known client-side (true/false, field.options.choices), but which of
  // those actually occur once OTHER columns are already filtered can only be
  // answered by the server (see otherFilters above).
  const { data: fetchedValues } = useQuery({
    queryKey: ["filter-values", field.id, "raw", otherFiltersKey],
    queryFn: async () =>
      (
        await apiClient.get<{ values: unknown[] }>(`/api/fields/${field.id}/filter-values`, {
          params: { apply_exclusion: false, filter: otherFiltersKey },
        })
      ).data.values,
    enabled: open,
  });

  const options = useMemo(() => {
    if (fetchedValues === undefined) return [];
    if (isBoolean) return fetchedValues.map((v) => ({ value: v, label: BOOLEAN_LABELS[String(v)] ?? String(v) }));
    if (isSingleSelect) {
      const choices = (field.options.choices as { value: string; label: string }[] | undefined) ?? [];
      return fetchedValues.map((v) => ({ value: v, label: choices.find((c) => c.value === v)?.label ?? String(v) }));
    }
    return fetchedValues.map((v) => ({ value: v, label: v == null ? "(empty)" : String(v) }));
  }, [isBoolean, isSingleSelect, field.options.choices, fetchedValues]);

  // Seeds the checklist once per open -- not on every options/currentValues
  // change, so a late-arriving fetch doesn't overwrite boxes the person has
  // already started unchecking. Waits for the fetch before seeding
  // "everything checked," rather than seeding against an empty list first
  // and then silently not-updating once real options land.
  useEffect(() => {
    if (!open) {
      initializedRef.current = false;
      return;
    }
    if (initializedRef.current) return;
    if (fetchedValues === undefined) return;
    setChecked(new Set((currentValues ?? options.map((o) => o.value)).map((v) => JSON.stringify(v))));
    setSearch("");
    initializedRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, fetchedValues]);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function handleScroll(e: Event) {
      // A scroll inside the checklist's own list (many values) must not
      // count as "scrolled away" -- only dismiss for scrolling outside this
      // panel (e.g. the grid body), same intent as DropdownMenu's own
      // scroll-dismiss.
      if (rootRef.current && rootRef.current.contains(e.target as Node)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("scroll", handleScroll, true);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("scroll", handleScroll, true);
    };
  }, [open]);

  const filteredOptions = search ? options.filter((o) => o.label.toLowerCase().includes(search.toLowerCase())) : options;

  function toggle(value: unknown) {
    const key = JSON.stringify(value);
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function handleApply() {
    if (checked.size === options.length) {
      onApply(null);
    } else {
      onApply(options.filter((o) => checked.has(JSON.stringify(o.value))).map((o) => o.value));
    }
    setOpen(false);
  }

  const isActive = currentValues !== null;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Filter this column"
        className={cn(
          "flex shrink-0 items-center rounded p-1 transition-colors hover:bg-surface-raised",
          isActive ? "text-accent-secondary" : "text-ink-tertiary",
        )}
      >
        <Filter className="size-3" fill={isActive ? "currentColor" : "none"} />
      </button>
      {open && (
        <div className="animate-dialog-panel absolute right-0 z-50 mt-1 w-56 rounded-xl border border-border-default bg-surface p-2 shadow-lg">
          <div className="relative mb-2">
            <Search className="absolute left-2 top-1/2 size-3 -translate-y-1/2 text-ink-tertiary" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search values…"
              className="py-1 pl-6 text-xs"
            />
          </div>
          <div className="mb-2 flex items-center gap-3 text-xs text-accent-secondary">
            <button type="button" onClick={() => setChecked(new Set(options.map((o) => JSON.stringify(o.value))))} className="hover:opacity-80">
              Select all
            </button>
            <button type="button" onClick={() => setChecked(new Set())} className="hover:opacity-80">
              Clear
            </button>
          </div>
          <div className="mb-2 max-h-56 space-y-0.5 overflow-y-auto">
            {filteredOptions.length === 0 ? (
              <p className="px-1 py-2 text-center text-xs text-ink-tertiary">No values</p>
            ) : (
              filteredOptions.map((o) => (
                <label
                  key={JSON.stringify(o.value)}
                  className="flex items-center gap-2 rounded-md px-1.5 py-1 text-xs text-ink-secondary hover:bg-surface-raised"
                >
                  <input
                    type="checkbox"
                    checked={checked.has(JSON.stringify(o.value))}
                    onChange={() => toggle(o.value)}
                    className="accent-accent-secondary"
                  />
                  <span className="truncate">{o.label}</span>
                </label>
              ))
            )}
          </div>
          <div className="flex gap-1.5">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="flex-1 rounded-md px-2 py-1 text-xs font-medium text-ink-secondary ring-1 ring-inset ring-border-default hover:bg-surface-raised"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleApply}
              className="flex-1 rounded-md bg-accent-secondary px-2 py-1 text-xs font-medium text-white hover:opacity-90"
            >
              Apply
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
