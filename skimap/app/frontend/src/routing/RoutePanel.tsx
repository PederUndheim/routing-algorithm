import { useState } from "react";
import type { ReactNode } from "react";

import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import CloseIcon from "@mui/icons-material/Close";

import { hasWidths } from "../corridorWidths";
import { isRoadRoute } from "../routes/routeList";
import type { Route } from "../routes/routeList";
import type {
  AddMode,
  CorridorWidth,
  CruxEntry,
  CruxNote,
  Factor,
  LatLng,
  PickMode,
  Rating,
  RouteNetwork,
  Waypoints,
} from "../types";
import { COLORS, PANEL_WIDTH } from "../theme";

import { DrawPane, GeneratePane, ModePicker, UploadPane } from "./AddRoute";
import { SectionHeading } from "./CollapseToggle";
import ResizeHandle from "./ResizeHandle";
import EditRouteBox from "./EditRouteBox";
import RouteListSection, { IdentifyButton } from "./RouteListSection";
import SelectedRoute, { CorridorControls, MakeCorridorButton } from "./SelectedRoute";
import Suggestions, { OptimiseButton } from "./Suggestions";
import type { SuggestionsProps } from "./Suggestions";
import { hintSx, scrollbarSx } from "./styles";

type RoutePanelProps = {
  open: boolean;
  onClose: () => void;
  panelWidth: number;
  onPanelWidthChange: (width: number) => void;
  onResetPanelWidth: () => void;
  addMode: AddMode;
  onAddModeChange: (mode: AddMode) => void;
  waypoints: Waypoints;
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  onPickPoints: () => void;
  onRemovePoint: (index: number) => void;
  onNetworkChange: (leg: number, network: RouteNetwork) => void;
  onClearPoints: () => void;
  onGenerate: () => void;
  isRouting: boolean;
  backendReady: boolean | null;
  isDrawing: boolean;
  onStartDrawing: () => void;
  draft: readonly LatLng[];
  /** A Route open for editing on the map, and how many points its line has. */
  editing: { name: string; points: number } | null;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
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
  onStartOver: () => void;
  activeCruxId: string | null;
  /** The Crux being edited, moved or having its extent edited, if any. */
  highlightedCruxId: string | null;
  onActivateCrux: (routeId: string, crux: CruxEntry) => void;
  onAnswer: (routeId: string, cruxId: string, factor: Factor, value: Rating | undefined) => void;
  onOverall: (routeId: string, cruxId: string, value: Rating | undefined) => void;
  onKeep: (routeId: string, cruxId: string, keep: boolean | undefined) => void;
  onNote: (routeId: string, cruxId: string, note: CruxNote, text: string) => void;
  onRestoreCrux: (routeId: string, cruxId: string) => void;
  onDeleteCrux: (routeId: string, cruxId: string) => void;
  onUndeleteCrux: (routeId: string, cruxId: string) => void;
  onEditCrux: (routeId: string, crux: CruxEntry) => void;
  onMoveCrux: (routeId: string, crux: CruxEntry) => void;
  onEditExtent: (routeId: string, crux: CruxEntry) => void;
  placingCrux: boolean;
  placingText: string;
  onPlaceCrux: () => void;
  /** The Add crux form for a spot just picked, or null. */
  addCruxForm: ReactNode;
  editingExtent: boolean;
  onFinishExtent: () => void;
  onResetExtent: () => void;
  showCorridor: boolean;
  onShowCorridorChange: (show: boolean) => void;
  corridorOpacity: number;
  onCorridorOpacityChange: (opacity: number) => void;
  corridorWidth: CorridorWidth;
  onCorridorWidthChange: (width: CorridorWidth) => void;
  isMakingCorridor: boolean;
  onMakeCorridor: () => void;
  /** Optimise route and what it found, for the Selected route - everything
   *  the Suggestions section needs but the suggestions, which are on it. */
  suggestionControls: Omit<SuggestionsProps, "suggestions">;
};

const RoutePanel = ({
  open,
  onClose,
  panelWidth,
  onPanelWidthChange,
  onResetPanelWidth,
  addMode,
  onAddModeChange,
  waypoints,
  pickMode,
  onPickModeChange,
  onPickPoints,
  onRemovePoint,
  onNetworkChange,
  onClearPoints,
  onGenerate,
  isRouting,
  backendReady,
  isDrawing,
  onStartDrawing,
  draft,
  editing,
  onSaveEdit,
  onCancelEdit,
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
  onStartOver,
  activeCruxId,
  highlightedCruxId,
  onActivateCrux,
  onAnswer,
  onOverall,
  onKeep,
  onNote,
  onRestoreCrux,
  onDeleteCrux,
  onUndeleteCrux,
  onEditCrux,
  onMoveCrux,
  onEditExtent,
  placingCrux,
  placingText,
  onPlaceCrux,
  addCruxForm,
  editingExtent,
  onFinishExtent,
  onResetExtent,
  showCorridor,
  onShowCorridorChange,
  corridorOpacity,
  onCorridorOpacityChange,
  corridorWidth,
  onCorridorWidthChange,
  isMakingCorridor,
  onMakeCorridor,
  suggestionControls,
}: RoutePanelProps) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  // A phone has no room to give the drawer, so there it is not resizable
  // and takes its usual share of the screen instead.
  const width = isMobile ? Math.min(window.innerWidth * 0.8, PANEL_WIDTH) : panelWidth;

  const selected = routes.find((r) => r.id === selectedId) ?? null;
  // Only for a line the router did not make: a routed one is already the
  // cheapest way on the same surface, so there would be nothing to find.
  // Not while a line is being edited - what it found describes the line
  // before the edit.
  const canOptimise = selected !== null && selected.routed === null && !editing;
  const optimiseButton = (
    <OptimiseButton
      isSearching={suggestionControls.isSearching}
      onSearch={suggestionControls.onSearch}
    />
  );
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
                  waypoints={waypoints}
                  pickMode={pickMode}
                  onPickModeChange={onPickModeChange}
                  onPickPoints={onPickPoints}
                  onRemovePoint={onRemovePoint}
                  onNetworkChange={onNetworkChange}
                  onClear={onClearPoints}
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
          banner={
            editing && (
              <EditRouteBox
                name={editing.name}
                points={editing.points}
                onSave={onSaveEdit}
                onCancel={onCancelEdit}
              />
            )
          }
        >
          {/* Part of the route part, folded with the list, and above the
              button so the Cruxes it finds come straight under it. A Route
              without a corridor gets the button that makes one in the same
              place, so the controls take over where it was once it is made;
              Optimise route sits beside it, or in a row of its own under the
              controls, which need the whole width. Rows are inset the same on
              either side - narrower than Identify cruxes below, and still
              centred under it - and of one fixed height, taller than the
              buttons, so swapping one for another moves nothing below it and
              the last one leaves the same room above Identify cruxes. */}
          {selected && (
            <Box sx={{ mt: 1, px: 2, height: 48, display: "flex", alignItems: "center", gap: 1 }}>
              {selected.corridor ? (
                <CorridorControls
                  showCorridor={showCorridor}
                  onShowCorridorChange={onShowCorridorChange}
                  corridorOpacity={corridorOpacity}
                  onCorridorOpacityChange={onCorridorOpacityChange}
                  corridorWidth={corridorWidth}
                  onCorridorWidthChange={onCorridorWidthChange}
                  widthsAvailable={hasWidths(selected.corridor)}
                />
              ) : isRoadRoute(selected) ? (
                // A terrain corridor around a drive would be ground the car
                // cannot go on. Edited, it is a drawn line and may have one.
                <Typography sx={{ ...hintSx, width: "100%", textAlign: "center" }}>
                  A drive stays on the road, so it has no corridor.
                </Typography>
              ) : (
                <>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <MakeCorridorButton isMaking={isMakingCorridor} onMake={onMakeCorridor} />
                  </Box>
                  {canOptimise && <Box sx={{ flex: 1, minWidth: 0 }}>{optimiseButton}</Box>}
                </>
              )}
            </Box>
          )}
          {canOptimise && selected.corridor && (
            <Box sx={{ px: 2, height: 48, display: "flex", alignItems: "center" }}>
              {optimiseButton}
            </Box>
          )}
          {canOptimise && selected.suggestions !== undefined && !suggestionControls.isSearching && (
            <Box sx={{ mt: 0.5, mb: 1, px: 2 }}>
              <Suggestions suggestions={selected.suggestions} {...suggestionControls} />
            </Box>
          )}
        </RouteListSection>

        <Box sx={{ mt: selected && routesOpen ? 1 : 2.5 }}>
          <IdentifyButton
            disabled={selected === null}
            identified={
              selected !== null &&
              (selected.crux !== null || selected.cruxes.some((c) => c.source === "identified"))
            }
            isIdentifying={isIdentifying}
            onIdentify={onIdentify}
            onStartOver={onStartOver}
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
            onNote={(cruxId, note, text) => onNote(selected.id, cruxId, note, text)}
            onRestoreCrux={(cruxId) => onRestoreCrux(selected.id, cruxId)}
            onDeleteCrux={(cruxId) => onDeleteCrux(selected.id, cruxId)}
            onUndeleteCrux={(cruxId) => onUndeleteCrux(selected.id, cruxId)}
            onEditCrux={(crux) => onEditCrux(selected.id, crux)}
            onMoveCrux={(crux) => onMoveCrux(selected.id, crux)}
            onEditExtent={(crux) => onEditExtent(selected.id, crux)}
            placingCrux={placingCrux}
            placingText={placingText}
            onPlaceCrux={onPlaceCrux}
            addCruxForm={addCruxForm}
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
