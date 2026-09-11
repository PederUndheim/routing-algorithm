import { divIcon } from "leaflet";
import { renderToStaticMarkup } from "react-dom/server";
import PlaceIcon from "@mui/icons-material/Place";
import FlagIcon from "@mui/icons-material/Flag";

import { COLORS } from "../theme";

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
