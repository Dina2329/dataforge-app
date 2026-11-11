import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../lib/apiClient";
import type { Notification } from "../types";

const POLL_INTERVAL_MS = 30000;

interface NotificationListResponse {
  notifications: Notification[];
  unread_count: number;
}

/** Polling, not a WebSocket channel -- an automation failure is inherently
 * rare and not latency-sensitive the way a live grid edit is, so a 30s
 * poll is simpler than adding a third real-time channel for one bell icon. */
export function useNotifications() {
  return useQuery({
    queryKey: ["notifications"],
    queryFn: async () => (await apiClient.get<NotificationListResponse>("/api/notifications")).data,
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (notificationId: string) => apiClient.post(`/api/notifications/${notificationId}/read`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => apiClient.post("/api/notifications/read-all"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
}
