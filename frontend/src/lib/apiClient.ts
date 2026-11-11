import axios, { AxiosError } from "axios";
import { useAuthStore } from "../stores/authStore";

// Same-origin by default (relative -- no host/port at all): Vite's dev
// server proxies /api and /ws through to the backend itself (see
// vite.config.ts), so the browser only ever needs to reach the one port it
// already loaded the page from. Hardcoding the backend's own port here
// instead would break under a LAN IP, an SSH tunnel, or VSCode's automatic
// port forwarding -- any of which can put the frontend and backend behind
// two *different* forwarded ports, or remap the backend's port entirely.
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "",
});

// Resolves to an absolute origin even when baseURL is relative -- needed
// anywhere a plain string concatenation isn't enough to build a URL (e.g.
// a WebSocket's ws:// scheme, which has no "relative" form).
export function apiOrigin(): string {
  return apiClient.defaults.baseURL || window.location.origin;
}

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshInFlight: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refreshToken = useAuthStore.getState().refreshToken;
  if (!refreshToken) throw new Error("No refresh token available");
  const { data } = await axios.post(`${apiClient.defaults.baseURL}/api/auth/refresh`, {
    refresh_token: refreshToken,
  });
  useAuthStore.getState().setAccessToken(data.access_token);
  return data.access_token;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (typeof error.config & { _retried?: boolean }) | undefined;
    if (error.response?.status === 401 && original && !original._retried) {
      original._retried = true;
      try {
        refreshInFlight ??= refreshAccessToken();
        const token = await refreshInFlight;
        refreshInFlight = null;
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${token}`;
        return apiClient.request(original);
      } catch {
        refreshInFlight = null;
        useAuthStore.getState().logout();
      }
    }
    return Promise.reject(error);
  },
);

export function apiErrorMessage(error: unknown, fallback = "Something went wrong"): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail;
    if (detail) return detail;
  }
  return fallback;
}
