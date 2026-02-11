import L from "leaflet";
import { renderToStaticMarkup } from "react-dom/server";
import PlaceIcon from "@mui/icons-material/Place";
import FlagIcon from "@mui/icons-material/Flag";

export const startIcon = L.divIcon({
  html: renderToStaticMarkup(
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 0,
        whiteSpace: "nowrap",
      }}
    >
      <PlaceIcon
        style={{
          color: "#367E98",
          fontSize: 56,
        }}
      />
      <span
        style={{
          fontSize: 14,
          fontWeight: 500,
          color: "white",
          background: "#555555",
          padding: "2px 6px",
          borderRadius: 6,
        }}
      >
        Start
      </span>
    </div>
  ),
  className: "",
  iconSize: [123, 56],
  iconAnchor: [28.5, 50],
});

export const endIcon = L.divIcon({
  html: renderToStaticMarkup(
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 3,
        whiteSpace: "nowrap",
      }}
    >
      <FlagIcon
        style={{
          color: "#EE7B04",
          fontSize: 56,
        }}
      />
      <span
        style={{
          fontSize: 14,
          fontWeight: 500,
          color: "white",
          background: "#555555",
          padding: "2px 6px",
          borderRadius: 6,
        }}
      >
        End
      </span>
    </div>
  ),
  className: "",
  iconSize: [123, 56],
  iconAnchor: [14, 48],
});
