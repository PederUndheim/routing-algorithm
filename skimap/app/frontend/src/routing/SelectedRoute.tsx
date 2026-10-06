import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import FormControlLabel from "@mui/material/FormControlLabel";
import Slider from "@mui/material/Slider";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";

import { cruxBadge, dangerIcons, dangerName } from "../dangerClasses";
import { km } from "../format";
import type { Route } from "../routes/routeList";
import type { Crux, CruxResult } from "../types";
import { COLORS, CRUX_COLORS, dangerColor } from "../theme";

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
        const icons = dangerIcons(crux);
        const badge = cruxBadge(crux);
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
                  backgroundColor: dangerColor(crux),
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
              {icons.map((AreaIcon, i) => (
                <AreaIcon key={i} sx={{ color: "white", fontSize: 18 }} />
              ))}
              <Typography sx={{ color: "white", fontSize: 13, flex: 1, textAlign: "left" }}>
                {dangerName(crux)}
                {badge && (
                  <Box component="span" sx={{ ml: 0.75, color: CRUX_COLORS.steep }}>
                    {badge}
                  </Box>
                )}
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

/** What the Selected route needs the drawer for: its Cruxes, its corridor,
 *  and the warning if part of it could not be analysed. The route's own
 *  numbers live behind the info button on its row in the list above, so the
 *  name is not repeated here. */
const SelectedRoute = ({ route, onFocusCrux, ...corridorControls }: SelectedRouteProps) => (
  <Box sx={{ mt: 2 }}>
    {/* A safety caveat, so never behind an info button. */}
    {route.crux && route.crux.no_data_m > 0 && (
      <Typography
        sx={{
          fontSize: 12,
          color: COLORS.orange,
          p: 1.5,
          borderRadius: 2,
          backgroundColor: "rgba(0,0,0,0.18)",
          border: "1px solid rgba(255,255,255,0.10)",
        }}
      >
        {km(route.crux.no_data_m)} of route not analysed: there is no terrain
        data there. It is drawn grey and dashed - do not read it as safe.
      </Typography>
    )}

    {route.crux && <CruxList result={route.crux} onFocus={onFocusCrux} />}

    {route.routed && <CorridorControls {...corridorControls} />}
  </Box>
);

export default SelectedRoute;
