import type { SvgIconComponent } from "@mui/icons-material";
import AirIcon from "@mui/icons-material/Air";
import PriorityHighIcon from "@mui/icons-material/PriorityHigh";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";

import type { DangerClass, Hazards, SegmentClass } from "./types";

/** A Crux or a segment: both carry a class and the same hazard marks, and
 *  everything here reads either. */
export type DangerArea = Hazards & { class: SegmentClass };

/** What each Danger class is called on screen - the names CONTEXT.md gives. */
export const DANGER_CLASS_NAMES: Record<DangerClass, string> = {
  steep_slope: "Steep slope",
  runout_area: "Runout area",
};

/** What an area is, in words: the marks first, because a release area on
 *  steep ground is a release area before it is steep. */
export const dangerName = (area: DangerArea): string => {
  if (area.class !== "steep_slope") {
    return DANGER_CLASS_NAMES[area.class as DangerClass] ?? "";
  }
  if (area.probable_release_area && area.fall_hazard) {
    return "Probable release area, fall hazard";
  }
  if (area.probable_release_area) return "Probable release area";
  if (area.fall_hazard) return "Fall hazard";
  return "Steep slope";
};

/** The icons a marker carries between its number and its degrees.
 *
 *  Plain steep ground gets none - the slope map underneath already shades
 *  it, and the degrees say the rest. What the area turns out to be is what
 *  is worth an icon, and it can be both at once. A Runout area has no
 *  degrees to show, so its icon is all it has.
 *
 *  A release area is an exclamation mark rather than a picture of a slide:
 *  at marker size a glyph reads where an illustration does not, and the
 *  degrees beside it already say what kind of ground it is. */
export const dangerIcons = (area: DangerArea): SvgIconComponent[] => {
  if (area.class === "runout_area") return [AirIcon];
  if (area.class !== "steep_slope") return [];
  const icons: SvgIconComponent[] = [];
  if (area.probable_release_area) icons.push(PriorityHighIcon);
  if (area.fall_hazard) icons.push(TrendingDownIcon);
  return icons;
};

/** How steep it gets, for a Steep slope area. The number is the point of
 *  the class, and it is what the slope map beneath is shaded by. */
export const cruxBadge = (area: DangerArea): string | null =>
  area.class === "steep_slope" && area.max_slope_deg !== undefined
    ? `${Math.round(area.max_slope_deg)}°`
    : null;
