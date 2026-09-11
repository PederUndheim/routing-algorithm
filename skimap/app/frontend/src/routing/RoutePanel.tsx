import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Slider from "@mui/material/Slider";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import CloseIcon from "@mui/icons-material/Close";

import type { LatLng, PickMode, RouteResponse } from "../types";
import { COLORS } from "../theme";

type RoutePanelProps = {
  open: boolean;
  onClose: () => void;
  startPoint: LatLng | null;
  endPoint: LatLng | null;
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  onClearStart: () => void;
  onClearEnd: () => void;
  onGenerate: () => void;
  isRouting: boolean;
  backendReady: boolean | null;
  result: RouteResponse | null;
  showCorridor: boolean;
  onShowCorridorChange: (show: boolean) => void;
  corridorOpacity: number;
  onCorridorOpacityChange: (opacity: number) => void;
};

const formatCoord = (p: LatLng) => p.lat.toFixed(4) + "°N, " + p.lng.toFixed(4) + "°E";

const km = (metres: number) => (metres / 1000).toFixed(2) + " km";

const pickLabel = (picking: boolean, chosen: boolean, what: string) => {
  if (picking) return "Click on map...";
  return (chosen ? "Re-pick " : "Pick ") + what;
};

const outlinedSx = {
  borderColor: COLORS.teal,
  color: "white",
  "&:hover": {
    borderColor: COLORS.teal,
    backgroundColor: "rgba(54,126,152,0.10)",
  },
  "&.Mui-disabled": { borderColor: "rgba(255,255,255,0.2)", color: "rgba(255,255,255,0.4)" },
};

type PointRowProps = {
  title: string;
  what: string;
  point: LatLng | null;
  picking: boolean;
  onPick: () => void;
  onClear: () => void;
};

const PointRow = ({ title, what, point, picking, onPick, onClear }: PointRowProps) => (
  <Box sx={{ mb: 2 }}>
    <Typography sx={{ color: "white", fontSize: { xs: 12, sm: 14 }, mb: 1 }}>
      {title}
    </Typography>

    <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
      <Button
        variant="outlined"
        fullWidth
        onClick={onPick}
        sx={{ ...outlinedSx, flex: 4, fontSize: { xs: 12, sm: 14 } }}
      >
        {pickLabel(picking, Boolean(point), what)}
      </Button>

      <Button
        variant="outlined"
        disabled={!point}
        onClick={onClear}
        sx={{
          ...outlinedSx,
          flex: 1,
          borderColor: "rgba(255,255,255,0.35)",
          fontSize: { xs: 12, sm: 14 },
        }}
      >
        Clear
      </Button>
    </Box>

    {/* Fixed height either way, so the panel does not jump as points land. */}
    <Typography
      sx={{
        mt: 0.75,
        minHeight: 18,
        fontSize: 12,
        color: point ? "rgba(255,255,255,0.75)" : "rgba(255,255,255,0.4)",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {point ? formatCoord(point) : "Not set - drag the marker to adjust it later."}
    </Typography>
  </Box>
);

const Readout = ({ label, value }: { label: string; value: string }) => (
  <Box sx={{ display: "flex", justifyContent: "space-between", py: 0.25 }}>
    <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.75)" }}>{label}</Typography>
    <Typography sx={{ fontSize: 13, color: "white", fontVariantNumeric: "tabular-nums" }}>
      {value}
    </Typography>
  </Box>
);

const RoutePanel = ({
  open,
  onClose,
  startPoint,
  endPoint,
  pickMode,
  onPickModeChange,
  onClearStart,
  onClearEnd,
  onGenerate,
  isRouting,
  backendReady,
  result,
  showCorridor,
  onShowCorridorChange,
  corridorOpacity,
  onCorridorOpacityChange,
}: RoutePanelProps) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const width = isMobile ? Math.min(window.innerWidth * 0.8, 380) : 380;

  const canRoute = Boolean(startPoint) && Boolean(endPoint) && !pickMode && !isRouting;

  return (
    <Drawer
      anchor="left"
      open={open}
      variant={isMobile ? "temporary" : "persistent"}
      onClose={onClose}
      ModalProps={{ keepMounted: true, hideBackdrop: !isMobile }}
      sx={{
        width,
        flexShrink: 0,
        "& .MuiDrawer-paper": {
          width,
          backgroundColor: COLORS.panel,
          display: "flex",
          flexDirection: "column",
          boxSizing: "border-box",
          borderRight: "1px solid rgba(0,0,0,0.12)",
        },
      }}
    >
      <Box sx={{ p: 2, pb: { xs: 1, sm: 2 }, display: "flex", alignItems: "center" }}>
        <Typography
          variant={isMobile ? "h6" : "h5"}
          sx={{ flex: 1, color: "white", fontWeight: 540 }}
        >
          Routing
        </Typography>
        <IconButton onClick={onClose}>
          <CloseIcon sx={{ color: "white" }} />
        </IconButton>
      </Box>

      <Divider color={COLORS.orange} variant="middle" />

      <Box sx={{ p: 2, display: "flex", flexDirection: "column", flex: 1, overflowY: "auto" }}>
        <PointRow
          title="Choose start point"
          what="start point"
          point={startPoint}
          picking={pickMode === "start"}
          onPick={() => onPickModeChange("start")}
          onClear={onClearStart}
        />

        <PointRow
          title="Choose end point"
          what="end point"
          point={endPoint}
          picking={pickMode === "end"}
          onPick={() => onPickModeChange("end")}
          onClear={onClearEnd}
        />

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

        <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.55)", mt: 0.5, mb: 2 }}>
          The corridor is the ground you could cross instead without the trip
          costing much more - navy along the route, fading out at the edge of
          the band, in the blue ArcGIS draws it. At 100% that is exactly the
          ArcGIS rendering. No parameters otherwise: the route is the cheapest
          line through the cost surface as it was last built.
        </Typography>

        <Box sx={{ mt: "auto" }}>
          {backendReady === false && (
            <Typography sx={{ fontSize: 12, color: COLORS.orange, mb: 1.5 }}>
              Backend not reachable on localhost:8000. Start it with
              {" python-qgis.bat -m app.backend.server"}, then reload.
            </Typography>
          )}

          <Button
            variant="contained"
            fullWidth
            size="large"
            disabled={!canRoute}
            onClick={onGenerate}
            sx={{
              backgroundColor: COLORS.orange,
              fontSize: { xs: 14, sm: 16 },
              "&:hover": { backgroundColor: COLORS.orange, transform: "scale(1.01)" },
              "&.Mui-disabled": {
                backgroundColor: "rgba(255,255,255,0.12)",
                color: "rgba(255,255,255,0.4)",
              },
            }}
          >
            {isRouting ? "Routing..." : "Generate route"}
          </Button>

          {result && (
            <Box
              sx={{
                mt: 2,
                p: 1.5,
                borderRadius: 2,
                backgroundColor: "rgba(0,0,0,0.18)",
                border: "1px solid rgba(255,255,255,0.10)",
              }}
            >
              <Readout label="Route length" value={km(result.length_m)} />
              <Readout label="Straight line" value={km(result.straight_m)} />
              <Readout label="Detour" value={result.detour.toFixed(2) + "x"} />
              <Readout label="Cost" value={Math.round(result.cost).toLocaleString()} />
              <Readout label="Routed in" value={result.seconds.toFixed(1) + " s"} />
            </Box>
          )}
        </Box>
      </Box>
    </Drawer>
  );
};

export default RoutePanel;
