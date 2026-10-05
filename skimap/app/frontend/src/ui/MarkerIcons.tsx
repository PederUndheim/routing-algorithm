import { divIcon } from "leaflet";
import type { DivIcon } from "leaflet";
import { renderToStaticMarkup } from "react-dom/server";
import PlaceIcon from "@mui/icons-material/Place";
import FlagIcon from "@mui/icons-material/Flag";

import { cruxBadge, dangerIcons } from "../dangerClasses";
import type { DangerArea } from "../dangerClasses";
import { COLORS, dangerColor } from "../theme";

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

/** A Crux pill's size in pixels.
 *
 *  Only ever an estimate - the pill is laid out `max-content` wide and the
 *  anchor is what places it - but it is the same estimate the clustering
 *  collides with, so markers merge roughly when they really would touch.
 *  One function, so the two can never drift apart. */
export const cruxIconSize = (
  area: DangerArea,
  selected: boolean,
  label = "0"
): [number, number] => {
  const height = selected ? 26 : 20;
  const marks = dangerIcons(area).length;
  const digits = Math.max(label.length - 1, 0) * 0.45;
  return [Math.round(height * (1 + digits + marks + (cruxBadge(area) ? 1.5 : 0))), height];
};

/** A Crux: a pill in its area's colour, its label, then what the area
 *  turns out to be and how steep it gets, with the label's disc centred on
 *  the point itself. `grouped` draws it as a stack, for several Cruxes too
 *  close together to draw apart - it then carries the worst of them.
 *
 *  Plain steep ground shows the degrees alone. A release area or a fall
 *  hazard puts its icon before them, both put both, and the pill turns red
 *  - so the icons say what kind of trouble and the number says how much. A
 *  Crux on a Route that is not selected is smaller and faded, so the
 *  Selected route's stand out. */
export const cruxIcon = (
  label: string,
  area: DangerArea,
  selected: boolean,
  grouped = false
): DivIcon => {
  const badge = cruxBadge(area);
  const icons = dangerIcons(area);
  const key = `${label}:${area.class}:${selected}:${badge ?? ""}:${
    area.probable_release_area ? "R" : ""
  }${area.fall_hazard ? "F" : ""}:${grouped}`;
  let icon = cruxIcons.get(key);
  if (!icon) {
    const [width, height] = cruxIconSize(area, selected, label);
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
            background: dangerColor(area),
            color: "white",
            fontSize: selected ? 13 : 11,
            fontWeight: 700,
            // A grouped marker is backed by a second and third outline,
            // so it reads as a stack of pills before the label is read.
            boxShadow: grouped
              ? `2px 2px 0 -1px ${dangerColor(area)}, 2px 2px 0 1px white,
                 4px 4px 0 -1px ${dangerColor(area)}, 4px 4px 0 1px white,
                 0 1px 4px rgba(0,0,0,0.45)`
              : "0 1px 4px rgba(0,0,0,0.45)",
            opacity: selected ? 1 : 0.6,
          }}
        >
          {/* Lighter than the rest: the number only tells you which Crux
              this is, while the degrees are the reading you came for. */}
          <span style={{ minWidth: height - 4, textAlign: "center", fontWeight: 500 }}>
            {label}
          </span>
          {icons.map((AreaIcon, i) => (
            <AreaIcon key={i} style={{ fontSize: selected ? 16 : 12 }} />
          ))}
          {badge && (
            <span style={{ paddingLeft: 1, fontVariantNumeric: "tabular-nums" }}>{badge}</span>
          )}
        </div>
      ),
      className: "",
      // Only a hint: the pill is max-content wide and the anchor below is
      // what actually places it, but Leaflet wants a size.
      iconSize: [width, height],
      iconAnchor: [height / 2, height / 2],
    });
    cruxIcons.set(key, icon);
  }
  return icon;
};
