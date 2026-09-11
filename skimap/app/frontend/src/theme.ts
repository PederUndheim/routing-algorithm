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

/** An analysed Route's colours: green where no Danger class applies, one
 *  red for every Danger class, grey where nothing is known. Apart from
 *  COLORS, which they do not replace - teal still means a Route that has not
 *  been analysed, orange still the thing to press. */
export const CRUX_COLORS = {
  none: "#2E9D4B",
  danger: "#D32F2F",
  noData: "#8C8C8C",
} as const;

/** The drawer's width wherever it is not a phone. The map needs it too, to
 *  keep what it zooms to out from under the drawer. */
export const PANEL_WIDTH = 380;

export const SHADOW = "0 8px 20px rgba(0,0,0,0.20)";
export const SHADOW_HOVER = "0 12px 28px rgba(0,0,0,0.25)";
