import { useMutation } from "@tanstack/react-query";
import { apiClient } from "../lib/apiClient";
import { useAuthStore } from "../stores/authStore";
import type { User } from "../types";

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

async function fetchMe(): Promise<User> {
  const { data } = await apiClient.get<User>("/api/auth/me");
  return data;
}

export function useLogin() {
  const setAuth = useAuthStore((s) => s.setAuth);
  return useMutation({
    mutationFn: async (payload: { email: string; password: string }) => {
      const { data } = await apiClient.post<TokenResponse>("/api/auth/login", payload);
      const user = await fetchMeWithToken(data.access_token);
      return { tokens: data, user };
    },
    onSuccess: ({ tokens, user }) => setAuth(tokens, user),
  });
}

export function useRegister() {
  const setAuth = useAuthStore((s) => s.setAuth);
  return useMutation({
    mutationFn: async (payload: { email: string; name: string; password: string }) => {
      const { data } = await apiClient.post<TokenResponse>("/api/auth/register", payload);
      const user = await fetchMeWithToken(data.access_token);
      return { tokens: data, user };
    },
    onSuccess: ({ tokens, user }) => setAuth(tokens, user),
  });
}

async function fetchMeWithToken(token: string): Promise<User> {
  const { data } = await apiClient.get<User>("/api/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return data;
}

export { fetchMe };
