import { create } from "zustand";

interface WorkspaceContextState {
  currentWorkspaceId: string | null;
  setCurrentWorkspaceId: (id: string | null) => void;
}

// Several routes (e.g. /tables/:tableId, /dashboards/:dashboardId) don't carry
// workspaceId in their own URL — the page fetches enough data to know its
// workspace and reports it here so the persistent sidebar can stay accurate
// without restructuring every route to nest under /workspaces/:workspaceId.
export const useWorkspaceContextStore = create<WorkspaceContextState>((set) => ({
  currentWorkspaceId: null,
  setCurrentWorkspaceId: (id) => set({ currentWorkspaceId: id }),
}));
