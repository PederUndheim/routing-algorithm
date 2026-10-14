import type { Corridor, CorridorImage, CorridorWidth } from "./types";

/** Narrowest first, the order the step slider runs in. */
export const CORRIDOR_WIDTHS: readonly CorridorWidth[] = ["narrow", "standard", "wide"];

/** What each step of the slider says under it. Short: it is a mark on a
 *  slider a few centimetres wide, not a description. */
export const CORRIDOR_WIDTH_LABELS: Record<CorridorWidth, string> = {
  narrow: "Narrow",
  standard: "Normal",
  wide: "Wide",
};

/** Whether this corridor came with a narrower and a wider band at all. One
 *  from an older backend has only the standard one, and the slider says so
 *  by standing still rather than by offering steps that change nothing. */
export const hasWidths = (corridor: Corridor): boolean =>
  !!corridor.widths?.narrow && !!corridor.widths?.wide;

/** The picture to draw for `width`, or the standard one where this corridor
 *  has none of that width. */
export const corridorImage = (corridor: Corridor, width: CorridorWidth): CorridorImage => {
  const picked = width === "standard" ? undefined : corridor.widths?.[width];
  return picked ?? { png_path: corridor.png_path, bounds: corridor.bounds };
};
