import { useState } from "react";
import { CheckCircle2, FileText } from "lucide-react";
import { useParams } from "react-router-dom";
import { usePublicForm, useSubmitPublicForm } from "../hooks/usePublicForm";
import { apiErrorMessage } from "../lib/apiClient";
import { PublicFormRenderer } from "../components/forms/PublicFormRenderer";
import { EmptyState } from "../components/shared/EmptyState";
import { PageSpinner } from "../components/shared/PageSpinner";

export function PublicFormPage() {
  const { token } = useParams<{ token: string }>();
  const { data: form, isLoading, isError, error } = usePublicForm(token);
  const submitForm = useSubmitPublicForm(token);
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas p-8">
        <EmptyState icon={FileText} title="Form not found" description={apiErrorMessage(error, "This form link is invalid or has been closed.")} />
      </div>
    );
  }

  if (isLoading || !form) {
    return (
      <div className="min-h-screen bg-canvas">
        <PageSpinner />
      </div>
    );
  }

  async function handleSubmit(values: Record<string, unknown>) {
    setSubmitError(null);
    try {
      await submitForm.mutateAsync(values);
      setSubmitted(true);
    } catch (err) {
      setSubmitError(apiErrorMessage(err, "Could not submit the form"));
    }
  }

  return (
    <div className="min-h-screen bg-canvas px-4 py-12">
      <div className="mx-auto max-w-xl">
        <div className="mb-4 flex items-center gap-2 text-xs text-ink-tertiary">
          <FileText className="size-3.5" /> {form.table_name} · DataForge
        </div>
        <div className="rounded-xl bg-surface p-6 shadow-sm border border-border-default">
          {submitted ? (
            <div className="flex flex-col items-center py-8 text-center">
              <CheckCircle2 className="mb-3 size-10 text-status-success" />
              <p className="text-base font-medium text-ink-primary">Thanks — your response was submitted.</p>
            </div>
          ) : (
            <>
              <h1 className="mb-1 text-lg font-semibold text-ink-primary">{form.view_name}</h1>
              {form.description && <p className="mb-4 text-sm text-ink-tertiary">{form.description}</p>}
              {submitError && <p className="mb-3 text-sm text-status-danger">{submitError}</p>}
              <PublicFormRenderer form={form} onSubmit={handleSubmit} submitting={submitForm.isPending} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
