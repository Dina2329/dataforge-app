const PALETTE = [
  "bg-fuchsia-600",
  "bg-emerald-600",
  "bg-amber-600",
  "bg-rose-600",
  "bg-sky-600",
  "bg-violet-600",
  "bg-teal-600",
];

function colorFor(seed: string): string {
  let hash = 0;
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return PALETTE[hash % PALETTE.length];
}

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

interface AvatarProps {
  name: string;
  size?: "sm" | "md";
}

export function Avatar({ name, size = "md" }: AvatarProps) {
  const dimension = size === "sm" ? "size-6 text-[10px]" : "size-8 text-xs";
  return (
    <span
      className={`inline-flex ${dimension} shrink-0 items-center justify-center rounded-full font-semibold text-white ${colorFor(name)}`}
    >
      {initialsFor(name || "?")}
    </span>
  );
}
