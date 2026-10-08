import { useState } from "react";

import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import CloseIcon from "@mui/icons-material/Close";

import type { Route } from "../routes/routeList";
import type { AddMode, CruxEntry, Factor, LatLng, PickMode, Rating } from "../types";
import { COLORS, PANEL_WIDTH } from "../theme";

import { DrawPane, GeneratePane, ModePicker, UploadPane } from "./AddRoute";
import { SectionHeading } from "./CollapseToggle";
import ResizeHandle from "./ResizeHandle";
import RouteListSection, { IdentifyButton } from "./RouteListSection";
import SelectedRoute, { CorridorControls } from "./SelectedRoute";
import { scrollbarSx } from "./styles";

type RoutePanelProps = {
  open: boolean;
  onClose: () => void;
  panelWidth: number;
  onPanelWidthChange: (width: number) => void;
  onResetPanelWidth: () => void;
  addMode: AddMode;
  onAddModeChange: (mode: AddMode) => void;
  startPoint: LatLng | null;
  endPoint: LatLng | null;
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  onClearStart: () => void;
  onClearEnd: () => void;
  onGenerate: () => void;
  isRouting: boolean;
  backendReady: boolean | null;
  isDrawing: boolean;
  onStartDrawing: () => void;
  draft: readonly LatLng[];
  editingName: string | null;
  onUndoDraft: () => void;
  onClearDraft: () => void;
  onFinishDraft: () => void;
  onCancelDraw: () => void;
  routes: readonly Route[];
  selectedId: string | null;
  onSelectRoute: (id: string) => void;
  onToggleRoute: (id: string) => void;
  onDeleteRoute: (id: string) => void;
  onEditRoute: (id: string) => void;
  onUpload: (files: File[]) => void;
  isIdentifying: boolean;
  onIdentify: () => void;
  activeCruxId: string | null;
  /** The Crux being edited, moved or having its extent edited, if any. */
  highlightedCruxId: string | null;
  onActivateCrux: (routeId: string, crux: CruxEntry) => void;
  onAnswer: (routeId: string, cruxId: string, factor: Factor, value: Rating | undefined) => void;
  onOverall: (routeId: string, cruxId: string, value: Rating | undefined) => void;
  onKeep: (routeId: string, cruxId: string, keep: boolean | undefined) => void;
  onRestoreCrux: (routeId: string, cruxId: string) => void;
  onDeleteCrux: (routeId: string, cruxId: string) => void;
  onUndeleteCrux: (routeId: string, cruxId: string) => void;
  onEditCrux: (routeId: string, crux: CruxEntry) => void;
  onMoveCrux: (routeId: string, crux: CruxEntry) => void;
  onEditExtent: (routeId: string, crux: CruxEntry) => void;
  placingCrux: boolean;
  placingText: string;
  onPlaceCrux: () => void;
  editingExtent: boolean;
  onFinishExtent: () => void;
  onResetExtent: () => void;
  showCorridor: boolean;
  onShowCorridorChange: (show: boolean) => void;
  corridorOpacity: number;
  onCorridorOpacityChange: (opacity: number) => void;
};

const RoutePanel = ({
  open,
  onClose,
  panelWidth,
  onPanelWidthChange,
  onResetPanelWidth,
  addMode,
  onAddModeChange,
  startPoint,
  endPoint,
  pickMode,
  onPickModeChange,
  onClearStart,
  onClearEnd,
  onGenerate,
  isRouting,
  backendReady,
  isDrawing,
  onStartDrawing,
  draft,
  editingName,
  onUndoDraft,
  onClearDraft,
  onFinishDraft,
  onCancelDraw,
  routes,
  selectedId,
  onSelectRoute,
  onToggleRoute,
  onDeleteRoute,
  onEditRoute,
  onUpload,
  isIdentifying,
  onIdentify,
  activeCruxId,
  highlightedCruxId,
  onActivateCrux,
  onAnswer,
  onOverall,
  onKeep,
  onRestoreCrux,
  onDeleteCrux,
  onUndeleteCrux,
  onEditCrux,
  onMoveCrux,
  onEditExtent,
  placingCrux,
  placingText,
  onPlaceCrux,
  editingExtent,
  onFinishExtent,
  onResetExtent,
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

  const selected = routes.find((r) => r.id === selectedId) ?? null;
  // Folding a section only hides it here: a line being drawn or a point
  // being picked carries on on the map.
  const [addOpen, setAddOpen] = useState(true);
  const [routesOpen, setRoutesOpen] = useState(true);

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
          Crux identifier
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
        <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.85)", mb: 2 }}>
          This application identifies the cruxes of a ski tour. Add a route by either automatic
          generation, drawing or uploading of GPX/GeoJSON.
        </Typography>

        <SectionHeading
          title="Add a route"
          open={addOpen}
          onToggle={() => setAddOpen((prev) => !prev)}
          what="the ways to add a route"
        />

        {addOpen && (
          <>
            <ModePicker mode={addMode} onChange={onAddModeChange} />

            <Box sx={{ mt: 1.5 }}>
              {addMode === "generate" && (
                <GeneratePane
                  startPoint={startPoint}
                  endPoint={endPoint}
                  pickMode={pickMode}
                  onPickModeChange={onPickModeChange}
                  onClearStart={onClearStart}
                  onClearEnd={onClearEnd}
                  onGenerate={onGenerate}
                  isRouting={isRouting}
                  backendReady={backendReady}
                />
              )}
              {addMode === "draw" && (
                <DrawPane
                  isDrawing={isDrawing}
                  onStart={onStartDrawing}
                  points={draft}
                  editingName={editingName}
                  onUndo={onUndoDraft}
                  onClear={onClearDraft}
                  onFinish={onFinishDraft}
                  onCancel={onCancelDraw}
                />
              )}
              {addMode === "upload" && <UploadPane onUpload={onUpload} />}
            </Box>
          </>
        )}

        <Divider sx={{ my: 2, borderColor: "rgba(255,255,255,0.15)" }} />

        <RouteListSection
          routes={routes}
          selectedId={selectedId}
          onSelect={onSelectRoute}
          onToggleVisible={onToggleRoute}
          onDelete={onDeleteRoute}
          onEdit={onEditRoute}
          open={routesOpen}
          onToggle={() => setRoutesOpen((prev) => !prev)}
        />

        {/* Above the button, so the button always closes the route part
            and the Cruxes it finds come straight under it. */}
        {selected?.routed && (
          <Box sx={{ mt: 1.5 }}>
            <CorridorControls
              showCorridor={showCorridor}
              onShowCorridorChange={onShowCorridorChange}
              corridorOpacity={corridorOpacity}
              onCorridorOpacityChange={onCorridorOpacityChange}
            />
          </Box>
        )}

        <Box sx={{ mt: selected?.routed ? 1.5 : 2.5 }}>
          <IdentifyButton
            disabled={selected === null}
            isIdentifying={isIdentifying}
            onIdentify={onIdentify}
          />
        </Box>

        {selected && (
          <SelectedRoute
            route={selected}
            activeCruxId={activeCruxId}
            highlightedCruxId={highlightedCruxId}
            onActivateCrux={(crux) => onActivateCrux(selected.id, crux)}
            onAnswer={(cruxId, factor, value) => onAnswer(selected.id, cruxId, factor, value)}
            onOverall={(cruxId, value) => onOverall(selected.id, cruxId, value)}
            onKeep={(cruxId, keep) => onKeep(selected.id, cruxId, keep)}
            onRestoreCrux={(cruxId) => onRestoreCrux(selected.id, cruxId)}
            onDeleteCrux={(cruxId) => onDeleteCrux(selected.id, cruxId)}
            onUndeleteCrux={(cruxId) => onUndeleteCrux(selected.id, cruxId)}
            onEditCrux={(crux) => onEditCrux(selected.id, crux)}
            onMoveCrux={(crux) => onMoveCrux(selected.id, crux)}
            onEditExtent={(crux) => onEditExtent(selected.id, crux)}
            placingCrux={placingCrux}
            placingText={placingText}
            onPlaceCrux={onPlaceCrux}
            editingExtent={editingExtent}
            onFinishExtent={onFinishExtent}
            onResetExtent={onResetExtent}
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
