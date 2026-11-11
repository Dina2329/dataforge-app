import { Monitor, Moon, Sun } from "lucide-react";
import { useThemeStore, type Theme } from "../../stores/themeStore";
import { cn } from "../../lib/cn";

const OPTIONS: { value: Theme; icon: typeof Sun; label: string }[] = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
  { value: "system", icon: Monitor, label: "System" },
];

export function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

  return (
    <div className="flex items-center gap-0.5 rounded-lg bg-surface-raised p-0.5">
      {OPTIONS.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          type="button"
          title={label}
          onClick={() => setTheme(value)}
          className={cn(
            "flex size-6 items-center justify-center rounded-md transition-colors",
            theme === value
              ? "bg-surface text-accent-secondary shadow-sm"
              : "text-ink-tertiary hover:text-ink-secondary",
          )}
        >
          <Icon className="size-3.5" />
        </button>
      ))}
    </div>
  );
}
