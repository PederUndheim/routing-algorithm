import type { SvgIconComponent } from "@mui/icons-material";
import LandslideIcon from "@mui/icons-material/Landslide";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import TsunamiIcon from "@mui/icons-material/Tsunami";

import type { DangerClass } from "./types";

/** What each Danger class is called on screen - the names CONTEXT.md gives. */
export const DANGER_CLASS_NAMES: Record<DangerClass, string> = {
  probable_release_area: "Probable release area",
  fall_hazard: "Fall hazard",
  runout_area: "Runout area",
};

/** One icon per Danger class, so a marker says which it is unopened: ground
 *  that slides, ground that drops away, and a flow that reaches you. */
export const DANGER_CLASS_ICONS: Record<DangerClass, SvgIconComponent> = {
  probable_release_area: LandslideIcon,
  fall_hazard: TrendingDownIcon,
  runout_area: TsunamiIcon,
};
