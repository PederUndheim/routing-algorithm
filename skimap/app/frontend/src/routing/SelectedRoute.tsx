import { useState } from "react";

import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Slider from "@mui/material/Slider";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";

import { km } from "../format";
import type { Route } from "../routes/routeList";
import type { CruxEntry, Factor } from "../types";
import { COLORS } from "../theme";
import CruxList from "./CruxList";

type CorridorControlsProps = {
  showCorridor: boolean;
  onShowCorridorChange: (show: boolean) => void;
  corridorOpacity: number;
  onCorridorOpacityChange: (opacity: number) => void;
};

/** A routed Route's corridor: on or off, and how strong. Compact - it is a
 *  setting, not something to read. */
export const CorridorControls = ({
  showCorridor,
  onShowCorridorChange,
  corridorOpacity,
  onCorridorOpacityChange,
}: CorridorControlsProps) => (
  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
    <FormControlLabel
      control={
        <Switch
          size="small"
          checked={showCorridor}
          onChange={(e) => onShowCorridorChange(e.target.checked)}
          sx={{
            "& .MuiSwitch-switchBase.Mui-checked": { color: COLORS.teal },
            "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": {
              backgroundColor: COLORS.teal,
            },
          }}
        />
      }
      label="Show corridor"
      sx={{
        color: "white",
        mr: 0,
        whiteSpace: "nowrap",
        "& .MuiFormControlLabel-label": { fontSize: 13 },
      }}
    />

    {/* Kept in the layout but dimmed when the corridor is off, so the
        panel does not jump as you toggle it - same as the map overlays. */}
    <Box
      sx={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        gap: 1.25,
        pl: 0.5,
        pr: 0.5,
        opacity: showCorridor ? 1 : 0.45,
        pointerEvents: showCorridor ? "auto" : "none",
        transition: "opacity 0.15s ease",
      }}
    >
      <Slider
        value={corridorOpacity}
        min={0}
        max={1}
        step={0.05}
        size="small"
        disabled={!showCorridor}
        onChange={(_, v) => onCorridorOpacityChange(v as number)}
        sx={{
          color: COLORS.teal,
          "& .MuiSlider-thumb": { width: 12, height: 12 },
        }}
      />
      <Typography
        sx={{
          fontSize: 12,
          color: "white",
          minWidth: 34,
          textAlign: "right",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {Math.round(corridorOpacity * 100)}%
      </Typography>
    </Box>
  </Box>
);

type SelectedRouteProps = {
  route: Route;
  activeCruxId: string | null;
  onActivateCrux: (crux: CruxEntry) => void;
  onAnswer: (cruxId: string, factor: Factor, value: boolean | undefined) => void;
  onRestoreCrux: (cruxId: string) => void;
  onRemoveCrux: (cruxId: string) => void;
  placingCrux: boolean;
  onPlaceCrux: () => void;
};

/** What the drawer shows for the Selected route below Identify cruxes: the
 *  warning if part of it could not be analysed, and its Cruxes. Highlighted
 *  in the list above, so the name is not repeated here. */
const SelectedRoute = ({
  route,
  activeCruxId,
  onActivateCrux,
  onAnswer,
  onRestoreCrux,
  onRemoveCrux,
  placingCrux,
  onPlaceCrux,
}: SelectedRouteProps) => {
  // Here rather than in the list, so it holds across switching routes and
  // a folded list gives its height back to the drawer.
  const [listOpen, setListOpen] = useState(true);
  const hasCruxes = route.cruxes.length > 0;

  return (
    <Box
      sx={{
        mt: 1.5,
        display: "flex",
        flexDirection: "column",
        gap: 1,
        // Fills the rest of the drawer. Below this the list would be too
        // short to use, so the drawer scrolls instead - only on a small screen.
        flex: 1,
        minHeight: hasCruxes && listOpen ? 180 : 0,
      }}
    >
      {/* A safety caveat, so always in plain sight. */}
      {route.crux && route.crux.no_data_m > 0 && (
        <Typography
          sx={{
            fontSize: 12,
            color: COLORS.orange,
            p: 1.5,
            borderRadius: 2,
            backgroundColor: "rgba(0,0,0,0.18)",
            border: "1px solid rgba(255,255,255,0.10)",
            flexShrink: 0,
          }}
        >
          {km(route.crux.no_data_m)} of route not analysed: there is no terrain
          data there. It is drawn grey and dashed - do not read it as safe.
        </Typography>
      )}

      <CruxList
        cruxes={route.cruxes}
        analysed={route.crux !== null}
        activeId={activeCruxId}
        onActivate={onActivateCrux}
        onAnswer={onAnswer}
        onRestore={onRestoreCrux}
        onRemove={onRemoveCrux}
        open={listOpen}
        onToggle={() => setListOpen((prev) => !prev)}
        placing={placingCrux}
        onPlace={onPlaceCrux}
      />
    </Box>
  );
};

export default SelectedRoute;
