import { divIcon } from "leaflet";
import type { DivIcon } from "leaflet";
import { renderToStaticMarkup } from "react-dom/server";
import PlaceIcon from "@mui/icons-material/Place";
import FlagIcon from "@mui/icons-material/Flag";

import { DANGER_CLASS_ICONS } from "../dangerClasses";
import type { DangerClass } from "../types";
import { COLORS, CRUX_COLORS } from "../theme";

const labelStyle = {
  fontSize: 14,
  fontWeight: 500,
  color: "white",
  background: COLORS.panel,
  padding: "2px 6px",
  borderRadius: 6,
} as const;

const rowStyle = {
  display: "flex",
  alignItems: "center",
  whiteSpace: "nowrap",
} as const;

export const startIcon = divIcon({
  html: renderToStaticMarkup(
    <div style={{ ...rowStyle, gap: 0 }}>
      <PlaceIcon style={{ color: COLORS.teal, fontSize: 56 }} />
      <span style={labelStyle}>Start</span>
    </div>
  ),
  className: "",
  iconSize: [123, 56],
  // The pin's point, not the box's corner: this is the pixel that gets routed.
  iconAnchor: [28.5, 50],
});

export const endIcon = divIcon({
  html: renderToStaticMarkup(
    <div style={{ ...rowStyle, gap: 3 }}>
      <FlagIcon style={{ color: COLORS.orange, fontSize: 56 }} />
      <span style={labelStyle}>End</span>
    </div>
  ),
  className: "",
  iconSize: [123, 56],
  iconAnchor: [14, 48],
});

// One icon per look rather than one per marker: re-running the identifier
// or switching the selection re-renders every marker.
const cruxIcons = new Map<string, DivIcon>();

/** A Crux: a red pill, its number then its Danger class's icon, with the
 *  number's disc centred on the point itself. A Crux on a Route that is not
 *  selected is smaller and faded, so the Selected route's stand out. */
export const cruxIcon = (number: number, dangerClass: DangerClass, selected: boolean): DivIcon => {
  const key = `${number}:${dangerClass}:${selected}`;
  let icon = cruxIcons.get(key);
  if (!icon) {
    const height = selected ? 26 : 20;
    const ClassIcon = DANGER_CLASS_ICONS[dangerClass];
    icon = divIcon({
      html: renderToStaticMarkup(
        <div
          style={{
            ...rowStyle,
            width: "max-content",
            gap: 1,
            height,
            boxSizing: "border-box",
            paddingRight: selected ? 6 : 4,
            borderRadius: height / 2,
            border: "2px solid white",
            background: CRUX_COLORS.danger,
            color: "white",
            fontSize: selected ? 13 : 11,
            fontWeight: 700,
            boxShadow: "0 1px 4px rgba(0,0,0,0.45)",
            opacity: selected ? 1 : 0.6,
          }}
        >
          <span style={{ minWidth: height - 4, textAlign: "center" }}>{number}</span>
          <ClassIcon style={{ fontSize: selected ? 16 : 12 }} />
        </div>
      ),
      className: "",
      iconSize: [height * 2, height],
      iconAnchor: [height / 2, height / 2],
    });
    cruxIcons.set(key, icon);
  }
  return icon;
};
