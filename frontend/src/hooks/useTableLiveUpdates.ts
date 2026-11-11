import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiOrigin } from "../lib/apiClient";
import { invalidateRecordsQueries } from "./useRecords";
import { useAuthStore } from "../stores/authStore";

const RECONNECT_DELAY_MS = 2000;

export interface PresenceUser {
  user_id: string;
  name: string;
  email: string;
}

export interface CellFocus {
  userId: string;
  rowId: number;
  fieldName: string;
}

interface LiveUpdatesResult {
  /** Other users currently connected to this table (self already excluded). */
  activeUsers: PresenceUser[];
  /** Latest known focused cell per user, keyed by user_id. */
  focusedCells: Map<string, CellFocus>;
  /** Tells peers "I'm now on this cell" -- a no-op while disconnected. */
  sendCellFocus: (rowId: number, fieldName: string) => void;
}

/** Live-refreshes the grid when anyone (including another tab/teammate)
 * creates, edits, or deletes a row on this table — a thin `{row_id}` nudge
 * over WebSocket that triggers the same TanStack Query invalidation a
 * manual edit already does, never a trusted diff applied client-side
 * (architecture plan, section 5: real-time updates stay thin, the client
 * always re-fetches through the normal permission-checked read path).
 *
 * The same connection also carries presence: who else has this table open,
 * and which cell each of them is currently on -- at-most-once, self-healing
 * on the next message, matching the backend's own tradeoff for this data. */
export function useTableLiveUpdates(tableId: string | undefined): LiveUpdatesResult {
  const queryClient = useQueryClient();
  const [activeUsers, setActiveUsers] = useState<PresenceUser[]>([]);
  const [focusedCells, setFocusedCells] = useState<Map<string, CellFocus>>(new Map());
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    setActiveUsers([]);
    setFocusedCells(new Map());
    if (!tableId) return;

    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;
    const selfId = useAuthStore.getState().user?.id;

    function connect() {
      const accessToken = useAuthStore.getState().accessToken;
      if (!accessToken) return;
      const wsBase = apiOrigin().replace(/^http/, "ws");
      socket = new WebSocket(`${wsBase}/ws/tables/${tableId}?token=${encodeURIComponent(accessToken)}`);
      socketRef.current = socket;

      socket.onmessage = (event) => {
        let msg: Record<string, unknown>;
        try {
          msg = JSON.parse(event.data);
        } catch {
          return;
        }
        switch (msg.type) {
          case "record_change":
            invalidateRecordsQueries(queryClient, tableId);
            return;
          case "presence_sync":
            setActiveUsers((msg.users as PresenceUser[]).filter((u) => u.user_id !== selfId));
            return;
          case "presence_join": {
            const user = msg.user as PresenceUser;
            if (user.user_id === selfId) return;
            setActiveUsers((prev) => [...prev.filter((u) => u.user_id !== user.user_id), user]);
            return;
          }
          case "presence_leave":
            setActiveUsers((prev) => prev.filter((u) => u.user_id !== msg.user_id));
            setFocusedCells((prev) => {
              if (!prev.has(msg.user_id as string)) return prev;
              const next = new Map(prev);
              next.delete(msg.user_id as string);
              return next;
            });
            return;
          case "cell_focus":
            setFocusedCells((prev) => {
              const next = new Map(prev);
              next.set(msg.user_id as string, { userId: msg.user_id as string, rowId: msg.row_id as number, fieldName: msg.field_name as string });
              return next;
            });
            return;
        }
      };
      socket.onclose = () => {
        if (!stopped) reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      };
    }

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
      socketRef.current = null;
    };
  }, [tableId, queryClient]);

  function sendCellFocus(rowId: number, fieldName: string) {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "cell_focus", row_id: rowId, field_name: fieldName }));
    }
  }

  return { activeUsers, focusedCells, sendCellFocus };
}
