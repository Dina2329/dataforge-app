import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "../types";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  setAuth: (tokens: { access_token: string; refresh_token: string }, user: User) => void;
  setAccessToken: (accessToken: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setAuth: (tokens, user) =>
        set({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token, user }),
      setAccessToken: (accessToken) => set({ accessToken }),
      logout: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    { name: "dataforge-auth" },
  ),
);
