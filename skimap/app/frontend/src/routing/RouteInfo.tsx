import { useState } from "react";
import type { ReactNode } from "react";

import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import { km } from "../format";
import type { Route } from "../routes/routeList";
import { COLORS } from "../theme";

/** An info button and what it says, which is on screen only while pressed.
 *  Description belongs behind this; a warning never does. */
export const InfoButton = ({ label, children }: { label: string; children: ReactNode }) => {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  return (
    <>
      <IconButton
        size="small"
        aria-label={label}
        onClick={(e) => {
          // On a route row the click would otherwise select the route too.
          e.stopPropagation();
          setAnchor(e.currentTarget);
        }}
        sx={{ p: 0.25, color: anchor ? COLORS.orange : "rgba(255,255,255,0.65)" }}
      >
        <InfoOutlinedIcon sx={{ fontSize: 18 }} />
      </IconButton>

      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{
          paper: {
            sx: {
              // Narrower than the drawer at its widest, so a paragraph in
              // here never turns into one very long line.
              maxWidth: 320,
              p: 1.5,
              backgroundColor: COLORS.panel,
              border: "1px solid rgba(255,255,255,0.15)",
              backgroundImage: "none",
            },
          },
        }}
      >
        {children}
      </Popover>
    </>
  );
};

const Readout = ({ label, value }: { label: string; value: string }) => (
  <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2, py: 0.25 }}>
    <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.75)" }}>{label}</Typography>
    <Typography sx={{ fontSize: 13, color: "white", fontVariantNumeric: "tabular-nums" }}>
      {value}
    </Typography>
  </Box>
);

/** What there is to know about one Route, on its own row in the list. An
 *  uploaded Route only has its length; the router's numbers exist only for
 *  one it computed. */
const RouteInfoButton = ({ route }: { route: Route }) => (
  <InfoButton label={`About ${route.name}`}>
    <Box sx={{ minWidth: 220 }}>
      <Typography
        sx={{ color: "white", fontSize: 13, fontWeight: 600, mb: 0.5, wordBreak: "break-word" }}
      >
        {route.name}
      </Typography>

      <Readout label="Route length" value={km(route.lengthM)} />
      {route.routed && (
        <>
          <Readout label="Straight line" value={km(route.routed.straight_m)} />
          <Readout label="Detour" value={route.routed.detour.toFixed(2) + "x"} />
          <Readout label="Cost" value={Math.round(route.routed.cost).toLocaleString()} />
          <Readout label="Routed in" value={route.routed.seconds.toFixed(1) + " s"} />
        </>
      )}
      {!route.routed && (
        <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.55)", mt: 0.5 }}>
          Uploaded, so there is nothing to say about how it was routed.
        </Typography>
      )}
    </Box>
  </InfoButton>
);

export default RouteInfoButton;
