import { useCallback, useEffect, useState } from "react";

import {
  PANEL_MAX_VIEWPORT_SHARE,
  PANEL_MAX_WIDTH,
  PANEL_MIN_WIDTH,
  PANEL_WIDTH,
} from "../theme";

const STORAGE_KEY = "skimap.panelWidth";

/** The widest the drawer may be right now. Capped by the viewport as well
 *  as absolutely, so a window that shrinks takes the drawer with it. */
const maxWidth = () =>
  Math.min(PANEL_MAX_WIDTH, Math.floor(window.innerWidth * PANEL_MAX_VIEWPORT_SHARE));

export const clampWidth = (width: number) =>
  Math.max(PANEL_MIN_WIDTH, Math.min(maxWidth(), Math.round(width)));

const stored = (): number => {
  // Private-mode browsers throw on access rather than returning null.
  try {
    const saved = Number(window.localStorage.getItem(STORAGE_KEY));
    return Number.isFinite(saved) && saved > 0 ? clampWidth(saved) : PANEL_WIDTH;
  } catch {
    return PANEL_WIDTH;
  }
};

/** The drawer's width, dragged by the user and remembered between visits.
 *
 * Re-clamped when the window resizes, so a drawer dragged wide on a big
 * screen does not swallow the map on a small one. The width is the app's,
 * not the drawer's, because the map insets what it zooms to by it. */
export const usePanelWidth = () => {
  const [width, setWidth] = useState(stored);

  const set = useCallback((next: number) => {
    const clamped = clampWidth(next);
    setWidth(clamped);
    try {
      window.localStorage.setItem(STORAGE_KEY, String(clamped));
    } catch {
      // Not being able to remember it is not a reason to refuse the drag.
    }
  }, []);

  const reset = useCallback(() => set(PANEL_WIDTH), [set]);

  useEffect(() => {
    const onResize = () => setWidth((prev) => clampWidth(prev));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return { width, setWidth: set, resetWidth: reset };
};
