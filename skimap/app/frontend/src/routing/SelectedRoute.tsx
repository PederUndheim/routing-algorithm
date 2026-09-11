import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import FormControlLabel from "@mui/material/FormControlLabel";
import Slider from "@mui/material/Slider";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";

import { DANGER_CLASS_ICONS, DANGER_CLASS_NAMES } from "../dangerClasses";
import { km } from "../format";
import type { Route } from "../routes/routeList";
import type { Crux, CruxResult } from "../types";
import { COLORS, CRUX_COLORS } from "../theme";

const Readout = ({ label, value }: { label: string; value: string }) => (
  <Box sx={{ display: "flex", justifyContent: "space-between", py: 0.25 }}>
    <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.75)" }}>{label}</Typography>
    <Typography sx={{ fontSize: 13, color: "white", fontVariantNumeric: "tabular-nums" }}>
      {value}
    </Typography>
  </Box>
);

type CorridorControlsProps = {
  showCorridor: boolean;
  onShowCorridorChange: (show: boolean) => void;
  corridorOpacity: number;
  onCorridorOpacityChange: (opacity: number) => void;
};

const CorridorControls = ({
  showCorridor,
  onShowCorridorChange,
  corridorOpacity,
  onCorridorOpacityChange,
}: CorridorControlsProps) => (
  <Box sx={{ mt: 1.5 }}>
    <FormControlLabel
      control={
        <Switch
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
      sx={{ color: "white", "& .MuiFormControlLabel-label": { fontSize: 14 } }}
    />

    {/* Kept in the layout but dimmed when the corridor is off, so the
        panel does not jump as you toggle it - same as the map overlays. */}
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        pl: 1.5,
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
        disabled={!showCorridor}
        onChange={(_, v) => onCorridorOpacityChange(v as number)}
        sx={{
          color: COLORS.teal,
          "& .MuiSlider-thumb": { width: 14, height: 14 },
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

    <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.55)", mt: 0.5 }}>
      The corridor is the ground you could cross instead without the trip
      costing much more - navy along the route, fading out at the edge of
      the band, in the blue ArcGIS draws it. At 100% that is exactly the
      ArcGIS rendering. No parameters otherwise: the route is the cheapest
      line through the cost surface as it was last built.
    </Typography>
  </Box>
);

/** The Selected route's Cruxes in route order, numbered like their markers.
 *  Clicking one takes the map there. */
const CruxList = ({ result, onFocus }: { result: CruxResult; onFocus: (crux: Crux) => void }) => (
  <Box sx={{ mt: 1.5 }}>
    <Typography sx={{ color: "white", fontSize: 14, fontWeight: 600, mb: 0.75 }}>
      Cruxes ({result.cruxes.length})
    </Typography>

    {result.cruxes.length === 0 && (
      <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.65)" }}>
        No Danger class along the analysed part of this route.
      </Typography>
    )}

    <Box
      component="ol"
      sx={{ listStyle: "none", p: 0, m: 0, display: "flex", flexDirection: "column", gap: 0.5 }}
    >
      {result.cruxes.map((crux) => {
        const ClassIcon = DANGER_CLASS_ICONS[crux.class];
        return (
          <Box component="li" key={crux.number}>
            <ButtonBase
              onClick={() => onFocus(crux)}
              sx={{
                width: "100%",
                justifyContent: "flex-start",
                gap: 1,
                px: 1,
                py: 0.5,
                borderRadius: 1.5,
                background: "rgba(255,255,255,0.06)",
                "&:hover": { background: "rgba(255,255,255,0.12)" },
              }}
            >
              <Box
                sx={{
                  minWidth: 22,
                  height: 22,
                  px: 0.5,
                  boxSizing: "border-box",
                  borderRadius: 11,
                  backgroundColor: CRUX_COLORS.danger,
                  color: "white",
                  fontSize: 12,
                  fontWeight: 700,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {crux.number}
              </Box>
              <ClassIcon sx={{ color: "white", fontSize: 18 }} />
              <Typography sx={{ color: "white", fontSize: 13, flex: 1, textAlign: "left" }}>
                {DANGER_CLASS_NAMES[crux.class]}
              </Typography>
              <Typography
                sx={{
                  color: "rgba(255,255,255,0.75)",
                  fontSize: 12,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {km(crux.distance_m)}
              </Typography>
            </ButtonBase>
          </Box>
        );
      })}
    </Box>
  </Box>
);

type SelectedRouteProps = CorridorControlsProps & {
  route: Route;
  onFocusCrux: (crux: Crux) => void;
};

/** What there is to know about the Selected route. An uploaded Route only
 *  has its length; the router's numbers and the corridor exist only for
 *  one it computed, and the Cruxes only once the identifier has run. */
const SelectedRoute = ({ route, onFocusCrux, ...corridorControls }: SelectedRouteProps) => (
  <Box sx={{ mt: 2 }}>
    <Box
      sx={{
        p: 1.5,
        borderRadius: 2,
        backgroundColor: "rgba(0,0,0,0.18)",
        border: "1px solid rgba(255,255,255,0.10)",
      }}
    >
      <Typography
        sx={{
          color: "white",
          fontSize: 14,
          fontWeight: 600,
          mb: 0.5,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
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

      {route.crux && route.crux.no_data_m > 0 && (
        <Typography sx={{ fontSize: 12, color: COLORS.orange, mt: 1 }}>
          {km(route.crux.no_data_m)} of route not analysed: there is no terrain
          data there. It is drawn grey and dashed - do not read it as safe.
        </Typography>
      )}
    </Box>

    {route.crux && <CruxList result={route.crux} onFocus={onFocusCrux} />}

    {route.routed && <CorridorControls {...corridorControls} />}
  </Box>
);

export default SelectedRoute;
