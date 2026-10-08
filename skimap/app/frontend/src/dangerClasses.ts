import type { SvgIconComponent } from "@mui/icons-material";
import AirIcon from "@mui/icons-material/Air";
import SignalCellular4BarIcon from "@mui/icons-material/SignalCellular4Bar";
import SignalCellularConnectedNoInternet4BarIcon from "@mui/icons-material/SignalCellularConnectedNoInternet4Bar";
import SevereColdIcon from "@mui/icons-material/SevereCold";
import SouthIcon from "@mui/icons-material/South";

import type { CruxProblem, DangerClass, Hazards, SegmentClass } from "./types";

/** The symbol for each problem, wherever it is drawn - marker, list, and
 *  the symbol picker. A slope is a filled triangle; a release area is that
 *  slope with an exclamation mark; a fall hazard is a straight drop; a
 *  runout is the air blast below a slide; a snow conditions check is a
 *  snowflake. */
export const PROBLEM_ICONS: Record<CruxProblem, SvgIconComponent> = {
  steep_slope: SignalCellular4BarIcon,
  release_area: SignalCellularConnectedNoInternet4BarIcon,
  fall_hazard: SouthIcon,
  runout_area: AirIcon,
  snow_check: SevereColdIcon,
};

/** A Crux or a segment: both carry a class and the same hazard marks, and
 *  everything here reads either. */
export type DangerArea = Hazards & {
  class: SegmentClass;
  /** A hand-placed Crux's own colour, in place of its class's. */
  color?: string;
};

/** What each Danger class is called on screen - the names CONTEXT.md gives. */
export const DANGER_CLASS_NAMES: Record<DangerClass, string> = {
  steep_slope: "Steep slope",
  runout_area: "Runout area",
};

/** What an area is, in words: the marks first, because a release area on
 *  steep ground is a release area before it is steep. */
export const dangerName = (area: DangerArea): string => {
  if (area.snow_check) return "Snow conditions check";
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

/** What a Crux is called in the list and its popup: the user's own words
 *  for one placed by hand, else what the identifier calls its area. */
export const cruxTitle = (crux: DangerArea & { description?: string }): string =>
  crux.description || dangerName(crux);

/** The icons a marker and a list row carry between the number and the
 *  degrees.
 *
 *  Plain steep ground gets the slope. A release area or a fall hazard gets
 *  its own instead - both already say the ground is steep - and an area can
 *  be both at once. A Runout area has no degrees to show, so its icon is all
 *  it has. */
export const dangerIcons = (area: DangerArea): SvgIconComponent[] => {
  if (area.snow_check) return [PROBLEM_ICONS.snow_check];
  if (area.class === "runout_area") return [PROBLEM_ICONS.runout_area];
  if (area.class !== "steep_slope") return [];
  const icons: SvgIconComponent[] = [];
  if (area.probable_release_area) icons.push(PROBLEM_ICONS.release_area);
  if (area.fall_hazard) icons.push(PROBLEM_ICONS.fall_hazard);
  return icons.length > 0 ? icons : [PROBLEM_ICONS.steep_slope];
};

/** How steep it gets, for a Steep slope area. The number is the point of
 *  the class, and it is what the slope map beneath is shaded by. */
export const cruxBadge = (area: DangerArea): string | null =>
  area.class === "steep_slope" && area.max_slope_deg !== undefined
    ? `${Math.round(area.max_slope_deg)}°`
    : null;
