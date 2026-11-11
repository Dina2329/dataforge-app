import { useEffect, useRef, useState } from "react";
import { ListChecks, Trash2 } from "lucide-react";
import { useParams } from "react-router-dom";
import { useMembers } from "../hooks/useMembers";
import {
  useDeletePrerequest,
  useMissingTermsApiConfig,
  usePrerequestUpload,
  useReplacePrerequest,
  useUpsertMissingTermsApiConfig,
} from "../hooks/useMissingTerms";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import { apiErrorMessage } from "../lib/apiClient";
import { useAuthStore } from "../stores/authStore";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { EmptyState } from "../components/shared/EmptyState";
import { PageHeader } from "../components/shared/PageHeader";

/** Owner/admin only -- the shared prerequest list AND the external lookup
 * API it feeds into are both one per workspace, used by every table's
 * Missing Terms Check. Real enforcement is server-side
 * (Permission.PREREQUEST_MANAGE); this page just doesn't show the controls
 * to a role that would only get a 403 from every action here. The API URL
 * is stored in the database (not an env var), so saving it here takes
 * effect immediately, no server restart needed. */
export function PrerequestPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  useReportWorkspaceContext(workspaceId);
  const currentUserId = useAuthStore((s) => s.user?.id);
  const { data: members } = useMembers(workspaceId);
  const currentRole = members?.find((m) => m.user_id === currentUserId)?.role;
  const canManage = currentRole === "owner" || currentRole === "admin";

  const { data: upload } = usePrerequestUpload(canManage ? workspaceId : undefined);
  const replacePrerequest = useReplacePrerequest(workspaceId);
  const deletePrerequest = useDeletePrerequest(workspaceId);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: apiConfig } = useMissingTermsApiConfig(canManage ? workspaceId : undefined);
  const upsertApiConfig = useUpsertMissingTermsApiConfig(workspaceId);
  const [apiUrl, setApiUrl] = useState("");
  const [apiError, setApiError] = useState<string | null>(null);

  const [confirming, setConfirming] = useState<File | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    setApiUrl(apiConfig?.api_url ?? "");
  }, [apiConfig]);

  function handlePick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) setConfirming(file);
  }

  async function handleConfirm() {
    if (!confirming) return;
    await replacePrerequest.mutateAsync(confirming);
    setConfirming(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleDelete() {
    await deletePrerequest.mutateAsync();
    setConfirmingDelete(false);
  }

  async function handleSaveApiUrl() {
    setApiError(null);
    try {
      await upsertApiConfig.mutateAsync({ api_url: apiUrl.trim(), headers: apiConfig?.headers ?? null });
    } catch (err) {
      setApiError(apiErrorMessage(err, "Could not save the external API settings"));
    }
  }

  if (!canManage) {
    return (
      <div className="p-6">
        <PageHeader title="Prerequest list" />
        <EmptyState icon={ListChecks} title="Owner/Admin only" description="Only a workspace owner or admin can view or manage the shared prerequest list." />
      </div>
    );
  }

  return (
    <div className="p-6">
      <PageHeader
        title="Prerequest list"
        description="The shared list of expected terms (Estate/Building/Unit/Sub-Domain/Term Name) every table's Missing Terms Check compares against."
      />

      <Card className="mb-4 p-5">
        {upload ? (
          <div className="flex items-start justify-between gap-4">
            <div className="text-sm text-ink-secondary">
              <p className="mb-1">
                <span className="font-medium text-ink-primary">{upload.original_filename}</span> — {upload.row_count} row{upload.row_count === 1 ? "" : "s"}
              </p>
              <p className="text-xs text-ink-tertiary">Uploaded {new Date(upload.uploaded_at).toLocaleString()}</p>
            </div>
            {!confirmingDelete ? (
              <Button size="sm" variant="danger" onClick={() => setConfirmingDelete(true)}>
                <Trash2 className="size-3.5" /> Delete
              </Button>
            ) : (
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-xs text-ink-secondary">Delete the whole list? Every table loses its comparison until a new one is uploaded.</span>
                <Button size="sm" variant="danger" loading={deletePrerequest.isPending} onClick={handleDelete}>
                  Confirm delete
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setConfirmingDelete(false)}>
                  Cancel
                </Button>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-ink-tertiary">No prerequest list uploaded yet.</p>
        )}
      </Card>

      <Card className="mb-4 p-5">
        <label className="mb-2 block text-xs font-medium text-ink-secondary">
          CSV columns required: Sub-Domain, Term Name. Optional: Estate, Building, Unit.
        </label>
        <input ref={fileInputRef} type="file" accept=".csv" onChange={handlePick} className="text-sm text-ink-secondary" />

        {confirming && (
          <div className="mt-3 flex items-center gap-2">
            <p className="text-xs text-ink-secondary">
              Replace the current list with <span className="font-medium">{confirming.name}</span>? This deletes every existing row.
            </p>
            <Button size="sm" loading={replacePrerequest.isPending} onClick={handleConfirm}>
              Confirm replace
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setConfirming(null)}>
              Cancel
            </Button>
          </div>
        )}
      </Card>

      <Card className="p-5">
        <label className="mb-1 block text-xs font-medium text-ink-secondary">External API</label>
        <p className="mb-2 text-xs text-ink-tertiary">
          Where the worker sends submitted rows for suggestions. One per workspace, used by every table here. Saving takes effect
          immediately -- no server restart needed.
        </p>
        <div className="flex gap-2">
          <Input value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} placeholder="https://example.com/lookup" className="flex-1" />
          <Button loading={upsertApiConfig.isPending} onClick={handleSaveApiUrl}>
            Save
          </Button>
        </div>
        {apiError && <p className="mt-2 text-xs text-status-danger">{apiError}</p>}
      </Card>
    </div>
  );
}
