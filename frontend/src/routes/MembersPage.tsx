import { useState } from "react";
import { ArrowLeft, ChevronDown, ChevronRight, Trash2, Users } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { WORKSPACE_ROLES, type WorkspaceRole } from "../types";
import {
  useAddTeamMember,
  useCreateTeam,
  useDeleteTeam,
  useInviteMember,
  useMembers,
  useRemoveMember,
  useRemoveTeamMember,
  useTeamMembers,
  useTeams,
  useUpdateMemberRole,
} from "../hooks/useMembers";
import { useReportWorkspaceContext } from "../hooks/useReportWorkspaceContext";
import { apiErrorMessage } from "../lib/apiClient";
import { useAuthStore } from "../stores/authStore";
import { Avatar } from "../components/ui/Avatar";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { PageHeader } from "../components/shared/PageHeader";
import { EmptyState } from "../components/shared/EmptyState";
import { ListRowsSkeleton } from "../components/ui/Skeleton";
import { ConfirmDeleteDialog } from "../components/shared/ConfirmDeleteDialog";

const ROLE_TONE: Record<WorkspaceRole, "accent" | "success" | "neutral"> = {
  owner: "accent",
  admin: "accent",
  editor: "success",
  viewer: "neutral",
};

function TeamRow({ workspaceId, teamId, teamName }: { workspaceId: string; teamId: string; teamName: string }) {
  const [expanded, setExpanded] = useState(false);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { data: members } = useTeamMembers(workspaceId, expanded ? teamId : undefined);
  const addMember = useAddTeamMember(workspaceId, teamId);
  const removeMember = useRemoveTeamMember(workspaceId, teamId);
  const deleteTeam = useDeleteTeam(workspaceId);

  async function handleAdd() {
    if (!email.trim()) return;
    setError(null);
    try {
      await addMember.mutateAsync(email.trim());
      setEmail("");
    } catch (err) {
      setError(apiErrorMessage(err, "Could not add member"));
    }
  }

  return (
    <Card>
      <div className="flex items-center justify-between">
        <button className="flex items-center gap-1.5 text-sm font-medium text-ink-primary" onClick={() => setExpanded(!expanded)}>
          {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          {teamName}
        </button>
        <Button variant="danger" size="sm" onClick={() => deleteTeam.mutate(teamId)}>
          <Trash2 className="size-3.5" />
        </Button>
      </div>
      {expanded && (
        <div className="mt-3 border-t border-border-default pt-3">
          <ul className="mb-3 space-y-1">
            {members?.map((m) => (
              <li key={m.user_id} className="flex items-center justify-between text-xs text-ink-secondary">
                <span className="flex items-center gap-2">
                  <Avatar name={m.name || m.email} size="sm" /> {m.email}
                </span>
                <button className="text-ink-tertiary hover:text-status-danger" onClick={() => removeMember.mutate(m.user_id)}>
                  Remove
                </button>
              </li>
            ))}
            {members?.length === 0 && <li className="text-xs text-ink-tertiary">No members yet.</li>}
          </ul>
          <div className="flex gap-2">
            <Input placeholder="user@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
            <Button variant="secondary" size="sm" loading={addMember.isPending} onClick={handleAdd}>
              Add
            </Button>
          </div>
          {error && <p className="mt-1 text-xs text-status-danger">{error}</p>}
        </div>
      )}
    </Card>
  );
}

export function MembersPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  useReportWorkspaceContext(workspaceId);
  const navigate = useNavigate();
  const currentUserId = useAuthStore((s) => s.user?.id);
  const { data: members, isLoading } = useMembers(workspaceId);
  const inviteMember = useInviteMember(workspaceId);
  const updateRole = useUpdateMemberRole(workspaceId);
  const removeMember = useRemoveMember(workspaceId);

  const { data: teams } = useTeams(workspaceId);
  const createTeam = useCreateTeam(workspaceId);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<WorkspaceRole>("editor");
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [teamName, setTeamName] = useState("");
  const [removeTarget, setRemoveTarget] = useState<{ userId: string; label: string } | null>(null);

  // Owner/admin are the only roles the backend lets manage members
  // (WORKSPACE_MANAGE_MEMBERS) -- editors and viewers get a 403 on every
  // action below, so there's no point showing them controls that can only
  // ever fail.
  const currentRole = members?.find((m) => m.user_id === currentUserId)?.role;
  const canManageMembers = currentRole === "owner" || currentRole === "admin";

  async function handleInvite() {
    if (!inviteEmail.trim()) return;
    setInviteError(null);
    try {
      await inviteMember.mutateAsync({ email: inviteEmail.trim(), role: inviteRole });
      setInviteEmail("");
    } catch (err) {
      setInviteError(apiErrorMessage(err, "Could not invite member"));
    }
  }

  async function handleCreateTeam() {
    if (!teamName.trim()) return;
    await createTeam.mutateAsync(teamName.trim());
    setTeamName("");
  }

  return (
    <div className="mx-auto max-w-3xl p-8">
      <button
        type="button"
        onClick={() => navigate(`/workspaces/${workspaceId}`)}
        className="mb-4 inline-flex items-center gap-1 text-xs text-ink-tertiary hover:text-ink-secondary"
      >
        <ArrowLeft className="size-3" /> Back
      </button>
      <PageHeader title="Members" description="Manage who has access to this workspace" />

      {canManageMembers && (
        <>
          <div className="mb-3 flex gap-2">
            <Input placeholder="user@example.com" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
            <div className="w-32 shrink-0">
              <Select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as WorkspaceRole)}>
                {WORKSPACE_ROLES.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </Select>
            </div>
            <Button loading={inviteMember.isPending} onClick={handleInvite}>
              Invite
            </Button>
          </div>
          {inviteError && <p className="mb-3 text-sm text-status-danger">{inviteError}</p>}
        </>
      )}

      {isLoading && <ListRowsSkeleton count={3} />}

      <div key={isLoading ? "loading" : "loaded"} className="animate-fade-in mb-10 space-y-2">
        {members?.map((member) => (
          <Card key={member.user_id} className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Avatar name={member.name || member.email} />
              <div>
                <p className="text-sm font-medium text-ink-primary">{member.name}</p>
                <p className="text-xs text-ink-tertiary">{member.email}</p>
              </div>
              <Badge tone={ROLE_TONE[member.role]}>{member.role}</Badge>
            </div>
            {canManageMembers && (
              <div className="flex items-center gap-2">
                <div className="w-28">
                  <Select
                    value={member.role}
                    onChange={(e) => updateRole.mutate({ userId: member.user_id, role: e.target.value as WorkspaceRole })}
                  >
                    {WORKSPACE_ROLES.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </Select>
                </div>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => setRemoveTarget({ userId: member.user_id, label: member.name || member.email })}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            )}
          </Card>
        ))}
      </div>

      <ConfirmDeleteDialog
        open={removeTarget !== null}
        onClose={() => setRemoveTarget(null)}
        onConfirm={() => {
          if (!removeTarget) return;
          removeMember.mutate(removeTarget.userId);
          setRemoveTarget(null);
        }}
        loading={removeMember.isPending}
        title="Remove member"
        description={removeTarget ? `This removes "${removeTarget.label}" from the workspace. They'll lose access immediately.` : ""}
      />

      <PageHeader title="Teams" description="Organize members into groups" />
      <div className="mb-3 flex gap-2">
        <Input placeholder="New team name" value={teamName} onChange={(e) => setTeamName(e.target.value)} />
        <Button loading={createTeam.isPending} onClick={handleCreateTeam}>
          Create
        </Button>
      </div>
      {teams?.length === 0 ? (
        <EmptyState icon={Users} title="No teams yet" />
      ) : (
        <div className="space-y-2">
          {workspaceId && teams?.map((team) => <TeamRow key={team.id} workspaceId={workspaceId} teamId={team.id} teamName={team.name} />)}
        </div>
      )}
    </div>
  );
}
