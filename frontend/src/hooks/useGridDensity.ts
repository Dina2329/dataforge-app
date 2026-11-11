import { useEffect, useState } from "react";

export const GRID_DENSITIES = ["compact", "comfortable", "spacious"] as const;
export type GridDensity = (typeof GRID_DENSITIES)[number];

export const DENSITY_ROW_HEIGHT: Record<GridDensity, number> = {
  compact: 28,
  comfortable: 34,
  spacious: 44,
};

const STORAGE_KEY = "dataforge-grid-density";

function readStored(): GridDensity {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return (GRID_DENSITIES as readonly string[]).includes(stored ?? "") ? (stored as GridDensity) : "comfortable";
  } catch {
    return "comfortable";
  }
}

/** A per-viewer row-height preference -- not collaborative data, so
 * localStorage (not the view's shared config) is the right place for it. */
export function useGridDensity(): [GridDensity, (density: GridDensity) => void] {
  const [density, setDensityState] = useState<GridDensity>(readStored);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, density);
    } catch {
      // Private-browsing/storage-blocked -- the preference just won't persist across reloads.
    }
  }, [density]);

  return [density, setDensityState];
}

const WRAP_STORAGE_KEY = "dataforge-grid-wrap-text";

function readStoredWrap(): boolean {
  try {
    return localStorage.getItem(WRAP_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

/** Same per-viewer-preference reasoning as density above -- whether long
 * cell content wraps (rows grow taller) or truncates is a personal
 * readability choice, not something that needs to look the same for every
 * collaborator on a shared view. */
export function useGridWrapText(): [boolean, (wrap: boolean) => void] {
  const [wrapText, setWrapTextState] = useState<boolean>(readStoredWrap);

  useEffect(() => {
    try {
      localStorage.setItem(WRAP_STORAGE_KEY, String(wrapText));
    } catch {
      // Private-browsing/storage-blocked -- the preference just won't persist across reloads.
    }
  }, [wrapText]);

  return [wrapText, setWrapTextState];
}
