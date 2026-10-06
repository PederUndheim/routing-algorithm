import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import CloseIcon from "@mui/icons-material/Close";

import type { Route } from "../routes/routeList";
import type { Crux, LatLng, PickMode } from "../types";
import { COLORS, PANEL_WIDTH } from "../theme";

import ResizeHandle from "./ResizeHandle";
import RouteListSection from "./RouteListSection";
import SelectedRoute from "./SelectedRoute";
import { outlinedSx, scrollbarSx } from "./styles";

type RoutePanelProps = {
  open: boolean;
  onClose: () => void;
  panelWidth: number;
  onPanelWidthChange: (width: number) => void;
  onResetPanelWidth: () => void;
  startPoint: LatLng | null;
  endPoint: LatLng | null;
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  onClearStart: () => void;
  onClearEnd: () => void;
  onGenerate: () => void;
  isRouting: boolean;
  backendReady: boolean | null;
  routes: readonly Route[];
  selectedId: string | null;
  onSelectRoute: (id: string) => void;
  onToggleRoute: (id: string) => void;
  onDeleteRoute: (id: string) => void;
  onUpload: (files: File[]) => void;
  isIdentifying: boolean;
  onIdentify: () => void;
  onFocusCrux: (routeId: string, crux: Crux) => void;
  showCorridor: boolean;
  onShowCorridorChange: (show: boolean) => void;
  corridorOpacity: number;
  onCorridorOpacityChange: (opacity: number) => void;
};

const formatCoord = (p: LatLng) => p.lat.toFixed(4) + "°N, " + p.lng.toFixed(4) + "°E";

const pickLabel = (picking: boolean, chosen: boolean, what: string) => {
  if (picking) return "Click on map...";
  return (chosen ? "Re-pick " : "Pick ") + what;
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
        size="small"
        fullWidth
        onClick={onPick}
        sx={{ ...outlinedSx, flex: 4, fontSize: 13 }}
      >
        {pickLabel(picking, Boolean(point), what)}
      </Button>

      <Button
        variant="outlined"
        size="small"
        disabled={!point}
        onClick={onClear}
        sx={{
          ...outlinedSx,
          flex: 1,
          borderColor: "rgba(255,255,255,0.35)",
          fontSize: 13,
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

const RoutePanel = ({
  open,
  onClose,
  panelWidth,
  onPanelWidthChange,
  onResetPanelWidth,
  startPoint,
  endPoint,
  pickMode,
  onPickModeChange,
  onClearStart,
  onClearEnd,
  onGenerate,
  isRouting,
  backendReady,
  routes,
  selectedId,
  onSelectRoute,
  onToggleRoute,
  onDeleteRoute,
  onUpload,
  isIdentifying,
  onIdentify,
  onFocusCrux,
  showCorridor,
  onShowCorridorChange,
  corridorOpacity,
  onCorridorOpacityChange,
}: RoutePanelProps) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  // A phone has no room to give the drawer, so there it is not resizable
  // and takes its usual share of the screen instead.
  const width = isMobile ? Math.min(window.innerWidth * 0.8, PANEL_WIDTH) : panelWidth;

  const canRoute = Boolean(startPoint) && Boolean(endPoint) && !pickMode && !isRouting;
  const selected = routes.find((r) => r.id === selectedId) ?? null;

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
          // The resize handle and its collapse tab ride just outside the
          // paper's right edge, and would be clipped away otherwise.
          overflow: "visible",
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

      <Box
        sx={{
          p: 2,
          display: "flex",
          flexDirection: "column",
          flex: 1,
          overflowY: "auto",
          ...scrollbarSx,
        }}
      >
        <Typography sx={{ color: "white", fontWeight: 600, fontSize: 16, mb: 1 }}>
          Generate route
        </Typography>

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

        {backendReady === false && (
          <Typography sx={{ fontSize: 12, color: COLORS.orange, mb: 1.5 }}>
            Backend not reachable on localhost:8000. Start it with
            {" python-qgis.bat -m app.backend.server"}, then reload.
          </Typography>
        )}

        <Button
          variant="contained"
          fullWidth
          size="small"
          disabled={!canRoute}
          onClick={onGenerate}
          sx={{
            backgroundColor: COLORS.orange,
            fontSize: 13,
            "&:hover": { backgroundColor: COLORS.orange, transform: "scale(1.01)" },
            "&.Mui-disabled": {
              backgroundColor: "rgba(255,255,255,0.12)",
              color: "rgba(255,255,255,0.4)",
            },
          }}
        >
          {isRouting ? "Routing..." : "Generate route"}
        </Button>

        <Divider sx={{ my: 2, borderColor: "rgba(255,255,255,0.15)" }} />

        <RouteListSection
          routes={routes}
          selectedId={selectedId}
          onSelect={onSelectRoute}
          onToggleVisible={onToggleRoute}
          onDelete={onDeleteRoute}
          onUpload={onUpload}
          isIdentifying={isIdentifying}
          onIdentify={onIdentify}
        />

        {selected && (
          <SelectedRoute
            route={selected}
            onFocusCrux={(crux) => onFocusCrux(selected.id, crux)}
            showCorridor={showCorridor}
            onShowCorridorChange={onShowCorridorChange}
            corridorOpacity={corridorOpacity}
            onCorridorOpacityChange={onCorridorOpacityChange}
          />
        )}
      </Box>

      {!isMobile && (
        <ResizeHandle
          width={panelWidth}
          onWidthChange={onPanelWidthChange}
          onReset={onResetPanelWidth}
          onCollapse={onClose}
        />
      )}
    </Drawer>
  );
};

export default RoutePanel;
