import { useState } from "react";
import { Check, Copy, Link2 } from "lucide-react";
import { useCreateShareLink, useRevokeShareLink } from "../../hooks/useDashboards";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Input } from "../ui/Input";

interface ShareDashboardDialogProps {
  dashboardId: string;
  shareToken: string | null;
  open: boolean;
  onClose: () => void;
}

export function ShareDashboardDialog({ dashboardId, shareToken, open, onClose }: ShareDashboardDialogProps) {
  const createShareLink = useCreateShareLink(dashboardId);
  const revokeShareLink = useRevokeShareLink(dashboardId);
  const [copied, setCopied] = useState(false);

  const shareUrl = shareToken ? `${window.location.origin}/share/dashboards/${shareToken}` : null;

  async function handleCopy() {
    if (!shareUrl) return;
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <Dialog open={open} onClose={onClose} title="Share dashboard">
      {shareUrl ? (
        <>
          <p className="mb-3 text-sm text-ink-secondary">
            Anyone with this link can view a read-only copy of this dashboard — no account needed.
          </p>
          <div className="mb-4 flex gap-2">
            <Input readOnly value={shareUrl} onFocus={(e) => e.target.select()} />
            <Button variant="secondary" onClick={handleCopy}>
              {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
            </Button>
          </div>
          <Button variant="danger" className="w-full" loading={revokeShareLink.isPending} onClick={() => revokeShareLink.mutate()}>
            Revoke link
          </Button>
        </>
      ) : (
        <>
          <p className="mb-4 text-sm text-ink-secondary">
            Create a public link so anyone can view this dashboard without signing in. Widget data stays live.
          </p>
          <Button className="w-full" loading={createShareLink.isPending} onClick={() => createShareLink.mutate()}>
            <Link2 className="size-4" /> Create share link
          </Button>
        </>
      )}
    </Dialog>
  );
}
