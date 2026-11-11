import { useEffect, useRef, useState } from "react";

const DURATION_MS = 600;
// Matches the --ease-snappy curve in index.css (cubic-bezier(0.2, 0, 0, 1))
// approximated in JS since CSS easing curves aren't reusable in a rAF loop.
function easeSnappy(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** Animates a displayed number toward `target` over ~600ms whenever it
 * changes, instead of the value just snapping -- used for KPI tiles so a
 * live-refetched dashboard number feels like it's updating, not reloading.
 * Non-numeric targets pass through unchanged (no animation to run). */
export function useCountUp(target: number | null): number | null {
  const [displayed, setDisplayed] = useState(target);
  const fromRef = useRef(target);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (target === null) {
      setDisplayed(null);
      return;
    }
    const targetValue = target;
    const from = fromRef.current ?? targetValue;
    if (from === targetValue) {
      setDisplayed(targetValue);
      return;
    }
    const start = performance.now();
    function tick(now: number) {
      const elapsed = now - start;
      const t = Math.min(1, elapsed / DURATION_MS);
      setDisplayed(from + (targetValue - from) * easeSnappy(t));
      if (t < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = targetValue;
      }
    }
    frameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  return displayed;
}
