import type { DangerArea } from "./dangerClasses";

/** The three colours the whole app is built from, in one place.
 *
 * Teal is the map furniture and the routed line, orange is the thing you
 * came here to press, grey is every panel behind them.
 */
export const COLORS = {
  teal: "#367E98",
  orange: "#EE7B04",
  panel: "#555555",
} as const;

/** An analysed Route's colours: green where nothing applies, red for steep
 *  ground that turns out to be a release area or a fall hazard, dark orange
 *  for steep ground that is merely steep, light orange for the lesser Runout
 *  area, grey where nothing is known. Apart from COLORS, which they do not
 *  replace - teal still means a Route that has not been analysed, and this
 *  orange is its own shade, not COLORS.orange (the button accent). */
export const CRUX_COLORS = {
  none: "#2E9D4B",
  danger: "#D32F2F",
  steep: "#E65100",
  runout: "#FFA726",
  noData: "#8C8C8C",
} as const;

/** The colour an area is drawn in, on the line and on its marker - one
 *  colour for the whole area, and the same one for both, so a marker never
 *  sits on a stretch of another colour.
 *
 *  Steep ground is red once it turns out to be a release area or a fall
 *  hazard, and dark orange while it is only steep. */
export const dangerColor = (area: DangerArea): string => {
  if (area.color) return area.color;
  switch (area.class) {
    case "none":
      return CRUX_COLORS.none;
    case "no_data":
      return CRUX_COLORS.noData;
    case "runout_area":
      return CRUX_COLORS.runout;
    default:
      return area.probable_release_area || area.fall_hazard
        ? CRUX_COLORS.danger
        : CRUX_COLORS.steep;
  }
};

/** A colour mixed towards white by `amount` (0-1), for text in a danger
 *  colour on the dark drawer, where the full shade reads too dim. Anything
 *  but a #rrggbb colour comes back as it is. */
export const lighten = (hex: string, amount: number): string => {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const mix = (c: number) => Math.round(c + (255 - c) * amount);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(mix);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
};

/** The drawer's width wherever it is not a phone - where it can be dragged
 *  wider, so this is only the starting point. The map needs the live width
 *  too, to keep what it zooms to out from under the drawer.
 *
 * The upper bound is also capped at a share of the viewport, so the drawer
 * can never take the map with it on a small screen. */
export const PANEL_WIDTH = 380;
export const PANEL_MIN_WIDTH = 280;
export const PANEL_MAX_WIDTH = 1100;
export const PANEL_MAX_VIEWPORT_SHARE = 0.58;

export const SHADOW = "0 8px 20px rgba(0,0,0,0.20)";
export const SHADOW_HOVER = "0 12px 28px rgba(0,0,0,0.25)";
