import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "light" | "dark" | "system";

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

function resolveIsDark(theme: Theme): boolean {
  if (theme === "system") return window.matchMedia("(prefers-color-scheme: dark)").matches;
  return theme === "dark";
}

function applyTheme(theme: Theme) {
  const isDark = resolveIsDark(theme);
  document.documentElement.classList.toggle("dark", isDark);
  document.documentElement.style.colorScheme = isDark ? "dark" : "light";
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: "system",
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },
    }),
    {
      name: "dataforge-theme",
      onRehydrateStorage: () => (state) => {
        if (state) applyTheme(state.theme);
      },
    },
  ),
);

// Keep "system" in sync with live OS-level changes (e.g. the OS switches
// from light to dark at sunset) without requiring a page reload.
if (typeof window !== "undefined") {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (useThemeStore.getState().theme === "system") applyTheme("system");
  });
  applyTheme(useThemeStore.getState().theme);
}
