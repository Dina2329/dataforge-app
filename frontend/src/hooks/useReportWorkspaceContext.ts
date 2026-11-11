import { useEffect } from "react";
import { useWorkspaceContextStore } from "../stores/workspaceContextStore";

export function useReportWorkspaceContext(workspaceId: string | null | undefined) {
  const setCurrentWorkspaceId = useWorkspaceContextStore((s) => s.setCurrentWorkspaceId);
  useEffect(() => {
    setCurrentWorkspaceId(workspaceId ?? null);
  }, [workspaceId, setCurrentWorkspaceId]);
}
