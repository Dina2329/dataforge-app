import { useState } from "react";
import { Check, Copy, Link2 } from "lucide-react";
import { useCreateViewShareLink, useRevokeViewShareLink } from "../../hooks/useBases";
import { PublicFormRenderer } from "../forms/PublicFormRenderer";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import type { Field, PublicForm, View } from "../../types";

interface FormViewPanelProps {
  tableId: string;
  view: View;
  fields: Field[];
  onSubmit: (values: Record<string, unknown>) => Promise<void>;
}

export function FormViewPanel({ tableId, view, fields, onSubmit }: FormViewPanelProps) {
  const createShareLink = useCreateViewShareLink(tableId);
  const revokeShareLink = useRevokeViewShareLink(tableId);
  const [copied, setCopied] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const fieldIds = view.config.field_ids ?? [];
  const formFields = fieldIds
    .map((id) => fields.find((f) => f.id === id))
    .filter((f): f is Field => !!f)
    .map((f) => ({ id: f.id, name: f.name, field_type: f.field_type, options: f.options, required: f.required }));

  const previewForm: PublicForm = {
    table_name: "",
    view_name: view.name,
    description: view.config.description ?? null,
    fields: formFields,
  };

  const shareUrl = view.share_token ? `${window.location.origin}/share/forms/${view.share_token}` : null;

  async function handleCopy() {
    if (!shareUrl) return;
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function handleSubmit(values: Record<string, unknown>) {
    setSubmitting(true);
    try {
      await onSubmit(values);
      setSubmitted(true);
      setTimeout(() => setSubmitted(false), 2000);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl">
      <div className="mb-4 rounded-xl bg-surface p-4 shadow-sm border border-border-default">
        {shareUrl ? (
          <>
            <p className="mb-2 text-xs font-medium text-ink-secondary">
              Anyone with this link can submit a new row — no account needed.
            </p>
            <div className="flex gap-2">
              <Input readOnly value={shareUrl} onFocus={(e) => e.target.select()} />
              <Button variant="secondary" onClick={handleCopy}>
                {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
              </Button>
              <Button variant="danger" loading={revokeShareLink.isPending} onClick={() => revokeShareLink.mutate(view.id)}>
                Revoke
              </Button>
            </div>
          </>
        ) : (
          <Button className="w-full" loading={createShareLink.isPending} onClick={() => createShareLink.mutate(view.id)}>
            <Link2 className="size-4" /> Create share link
          </Button>
        )}
      </div>

      <div className="rounded-xl bg-surface p-6 shadow-sm border border-border-default">
        <h2 className="mb-1 text-lg font-semibold text-ink-primary">{view.name}</h2>
        {view.config.description && <p className="mb-4 text-sm text-ink-tertiary">{view.config.description}</p>}
        {submitted && <p className="mb-3 rounded-lg bg-status-success-tint px-3 py-2 text-sm text-status-success">Row added.</p>}
        <PublicFormRenderer form={previewForm} onSubmit={handleSubmit} submitting={submitting} submitLabel="Add row (preview)" />
      </div>
    </div>
  );
}
