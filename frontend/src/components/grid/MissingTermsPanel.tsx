import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  useCreateMissingTermsJob,
  useIgnoreMissingTerm,
  useIgnoredMissingTerms,
  useManualInsertMissingTerm,
  useMissingTerms,
  useMissingTermsConfig,
  useUnignoreMissingTerm,
} from "../../hooks/useMissingTerms";
import { apiErrorMessage } from "../../lib/apiClient";
import { toast } from "../../stores/toastStore";
import type { Field } from "../../types";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";

const EXCLUDED_FIELD_TYPES = new Set(["link_to_record", "lookup", "rollup", "formula", "attachment"]);

interface MissingTermsPanelProps {
  tableId: string;
  fields: Field[];
  collapsed: boolean;
  onToggleCollapse: () => void;
}

/** Inline, full-width, retractable panel (collapsing hides the body without
 * unmounting the component, so the current selection survives) shown
 * between the view tabs and the main grid. Rather than one card per missing
 * term (unworkable once there are many), a single form: pick a Sub-Domain,
 * then a Term Name filtered down to just the missing ones under it, fill in
 * Page/PDF-Image/PDF Name/Keywords, and submit that one term right away -- or flip to
 * manual mode and save it to the main table directly, duplicate-checked
 * either way. Submitting clears the selection so the next term can be
 * picked immediately. */
export function MissingTermsPanel({ tableId, fields, collapsed, onToggleCollapse }: MissingTermsPanelProps) {
  const [manualMode, setManualMode] = useState(false);
  const [selectedSubDomain, setSelectedSubDomain] = useState("");
  const [selectedTermName, setSelectedTermName] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showIgnored, setShowIgnored] = useState(false);

  const { data: config } = useMissingTermsConfig(tableId);
  const { data } = useMissingTerms(tableId);
  const { data: ignoredTerms } = useIgnoredMissingTerms(tableId, showIgnored);
  const createJob = useCreateMissingTermsJob(tableId);
  const manualInsert = useManualInsertMissingTerm(tableId);
  const ignoreTerm = useIgnoreMissingTerm(tableId);
  const unignoreTerm = useUnignoreMissingTerm(tableId);

  const tableFields = fields.filter((f) => !EXCLUDED_FIELD_TYPES.has(f.field_type));
  const subDomainFieldId = config?.field_mapping.sub_domain;
  const termNameFieldId = config?.field_mapping.term_name;
  const manualFields = tableFields.filter((f) => f.id !== subDomainFieldId && f.id !== termNameFieldId);

  const subDomains = useMemo(() => Array.from(new Set((data?.rows ?? []).map((r) => r.sub_domain))).sort(), [data]);
  const termNames = useMemo(
    () => (data?.rows ?? []).filter((r) => r.sub_domain === selectedSubDomain).map((r) => r.term_name).sort(),
    [data, selectedSubDomain],
  );
  const selectedRow = (data?.rows ?? []).find((r) => r.sub_domain === selectedSubDomain && r.term_name === selectedTermName);

  // A fresh Sub-Domain invalidates whatever Term Name was picked under the
  // previous one; a fresh Term Name starts this term's form blank.
  useEffect(() => {
    setSelectedTermName("");
  }, [selectedSubDomain]);
  useEffect(() => {
    setValues({});
    setSubmitError(null);
  }, [selectedSubDomain, selectedTermName]);

  function resetSelection() {
    setSelectedSubDomain("");
    setSelectedTermName("");
    setValues({});
  }

  async function handleSendForSuggestions() {
    if (!selectedRow) return;
    if (!(values.page || values.pdf_image || values.pdf_name || values.keywords)) {
      setSubmitError("Fill in at least one of Page / PDF-Image / PDF Name / Keywords first");
      return;
    }
    setSubmitError(null);
    try {
      await createJob.mutateAsync([
        {
          sub_domain: selectedRow.sub_domain,
          term_name: selectedRow.term_name,
          estate: selectedRow.estate,
          building: selectedRow.building,
          unit: selectedRow.unit,
          page: values.page ?? null,
          pdf_image: values.pdf_image ?? null,
          pdf_name: values.pdf_name ?? null,
          keywords: values.keywords ?? null,
        },
      ]);
      toast.success("Submitted -- you'll be notified when it's ready to review");
      resetSelection();
    } catch (err) {
      setSubmitError(apiErrorMessage(err, "Could not submit this row"));
    }
  }

  async function handleIgnore() {
    if (!selectedRow) return;
    setSubmitError(null);
    try {
      await ignoreTerm.mutateAsync({ sub_domain: selectedRow.sub_domain, term_name: selectedRow.term_name });
      toast.success("Ignored -- won't show up as missing anymore");
      resetSelection();
    } catch (err) {
      setSubmitError(apiErrorMessage(err, "Could not ignore this term"));
    }
  }

  async function handleSaveToMainTable() {
    if (!selectedRow) return;
    setSubmitError(null);
    try {
      await manualInsert.mutateAsync({ sub_domain: selectedRow.sub_domain, term_name: selectedRow.term_name, values });
      toast.success("Saved to main table");
      resetSelection();
    } catch (err) {
      setSubmitError(apiErrorMessage(err, "Could not save this row"));
    }
  }

  const notConfigured = config == null || !subDomainFieldId || !termNameFieldId;

  return (
    <div className="mb-4 rounded-xl border border-border-default bg-surface p-4 shadow-sm">
      <div className={collapsed ? "flex items-center justify-between" : "mb-3 flex items-center justify-between"}>
        <button type="button" onClick={onToggleCollapse} className="flex items-center gap-1.5 text-sm font-semibold text-ink-primary">
          {collapsed ? <ChevronRight className="size-4 text-ink-tertiary" /> : <ChevronDown className="size-4 text-ink-tertiary" />}
          Missing Terms Check
        </button>
      </div>

      {!collapsed && notConfigured && (
        <p className="text-xs text-status-warning">
          Map Sub-Domain and Term Name to real fields in "Missing Terms config" (in the "More ▾" menu) before using this.
        </p>
      )}

      {!collapsed && !notConfigured && data && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-4 text-xs text-ink-secondary">
            <span>Total: {data.summary.total}</span>
            <span>Matched: {data.summary.matched}</span>
            <span className="font-medium text-ink-primary">Missing: {data.summary.missing}</span>
            <span>In progress: {data.summary.in_progress}</span>
            <button type="button" className="underline-offset-2 hover:underline" onClick={() => setShowIgnored((v) => !v)}>
              Ignored: {data.summary.ignored}
            </button>
            <label className="ml-auto flex items-center gap-1.5">
              <input type="checkbox" checked={manualMode} onChange={(e) => setManualMode(e.target.checked)} className="accent-accent-secondary" />
              Manual entry
            </label>
          </div>

          {showIgnored && (
            <div className="mb-4 max-h-40 space-y-1 overflow-y-auto rounded-lg border border-border-default p-2">
              {(ignoredTerms ?? []).length === 0 ? (
                <p className="py-2 text-center text-xs text-ink-tertiary">Nothing ignored.</p>
              ) : (
                (ignoredTerms ?? []).map((t) => (
                  <div key={`${t.sub_domain}\u0001${t.term_name}`} className="flex items-center justify-between gap-2 rounded px-2 py-1 text-xs">
                    <span className="truncate text-ink-secondary">
                      {t.sub_domain} / {t.term_name}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={unignoreTerm.isPending}
                      onClick={() => unignoreTerm.mutate({ sub_domain: t.sub_domain, term_name: t.term_name })}
                    >
                      Revert
                    </Button>
                  </div>
                ))
              )}
            </div>
          )}

          {subDomains.length === 0 ? (
            <p className="py-6 text-center text-xs text-ink-tertiary">Nothing missing.</p>
          ) : (
            <>
              <div className="mb-4 grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-ink-secondary">Sub-Domain</label>
                  <Select value={selectedSubDomain} onChange={(e) => setSelectedSubDomain(e.target.value)}>
                    <option value="">— pick a Sub-Domain ({subDomains.length} with something missing) —</option>
                    {subDomains.map((sd) => (
                      <option key={sd} value={sd}>
                        {sd}
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-ink-secondary">Term Name</label>
                  <Select value={selectedTermName} onChange={(e) => setSelectedTermName(e.target.value)} disabled={!selectedSubDomain}>
                    <option value="">{selectedSubDomain ? `— pick a Term Name (${termNames.length} missing) —` : "— pick a Sub-Domain first —"}</option>
                    {termNames.map((tn) => (
                      <option key={tn} value={tn}>
                        {tn}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>

              {selectedRow && (
                <div className="rounded-lg border border-border-default p-3">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-3 text-xs text-ink-tertiary">
                      {selectedRow.estate && <span>Estate: {selectedRow.estate}</span>}
                      {selectedRow.building && <span>Building: {selectedRow.building}</span>}
                      {selectedRow.unit && <span>Unit: {selectedRow.unit}</span>}
                    </div>
                    <Button variant="ghost" size="sm" loading={ignoreTerm.isPending} onClick={handleIgnore}>
                      Ignore this term
                    </Button>
                  </div>

                  {submitError && <p className="mb-3 text-sm text-status-danger">{submitError}</p>}

                  {!manualMode ? (
                    <>
                      <div className="mb-3 grid grid-cols-2 gap-2 md:grid-cols-4">
                        <div>
                          <label className="mb-1 block text-xs font-medium text-ink-secondary">Page</label>
                          <Input value={values.page ?? ""} onChange={(e) => setValues((prev) => ({ ...prev, page: e.target.value }))} />
                        </div>
                        <div>
                          <label className="mb-1 block text-xs font-medium text-ink-secondary">PDF/Image</label>
                          <Select value={values.pdf_image ?? ""} onChange={(e) => setValues((prev) => ({ ...prev, pdf_image: e.target.value }))}>
                            <option value="">— select —</option>
                            <option value="PDF">PDF</option>
                            <option value="Image">Image</option>
                          </Select>
                        </div>
                        <div>
                          <label className="mb-1 block text-xs font-medium text-ink-secondary">PDF Name</label>
                          <Input value={values.pdf_name ?? ""} onChange={(e) => setValues((prev) => ({ ...prev, pdf_name: e.target.value }))} />
                        </div>
                        <div>
                          <label className="mb-1 block text-xs font-medium text-ink-secondary">Keywords</label>
                          <Input value={values.keywords ?? ""} onChange={(e) => setValues((prev) => ({ ...prev, keywords: e.target.value }))} placeholder="comma, separated" />
                        </div>
                      </div>
                      <Button onClick={handleSendForSuggestions} loading={createJob.isPending} className="w-full">
                        Send for suggestions
                      </Button>
                    </>
                  ) : (
                    <>
                      <div className="mb-3 grid grid-cols-2 gap-2 md:grid-cols-3">
                        {manualFields.map((f) => (
                          <div key={f.id}>
                            <label className="mb-1 block text-xs font-medium text-ink-secondary">{f.name}</label>
                            <Input value={values[f.name] ?? ""} onChange={(e) => setValues((prev) => ({ ...prev, [f.name]: e.target.value }))} />
                          </div>
                        ))}
                      </div>
                      <Button onClick={handleSaveToMainTable} loading={manualInsert.isPending} className="w-full">
                        Save to main table
                      </Button>
                    </>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
