import { useMemo, useRef, useState } from "react";
import { MapContainer, Marker, Pane, TileLayer } from "react-leaflet";
import type { DivIcon, LatLngTuple, Marker as LeafletMarker } from "leaflet";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";

import { getBasemap } from "../layers/basemaps";
import type { BasemapId } from "../layers/basemaps";
import { OVERLAYS } from "../layers/overlays";
import type { OverlayId } from "../layers/overlays";
import type { Route } from "../routes/routeList";
import type { RouteSuggestion } from "../routes/suggestions";
import type { LineString } from "geojson";

import type { AddMode, CorridorImage, Extent, LatLng, MapFocus } from "../types";
import { COLORS } from "../theme";

import { endIcon, startIcon, waypointIcon } from "../ui/MarkerIcons";
import CursorCoords from "../ui/CursorCoords";
import MapClickPicker from "../ui/MapClickPicker";
import RoutingButton from "../ui/RoutingButton";
import ScaleBar from "../ui/ScaleBar";

import CorridorOverlay from "./CorridorOverlay";
import CruxMarkers from "./CruxMarkers";
import CruxPlacer from "./CruxPlacer";
import ExtentEditor from "./ExtentEditor";
import DrawLayer from "./DrawLayer";
import FocusController from "./FocusController";
import IndexedTileLayer from "./IndexedTileLayer";
import LayerControl from "./LayerControl";
import MapActions from "./MapActions";
import MapController from "./MapController";
import RouteLines from "./RouteLines";
import SuggestionLines from "./SuggestionLines";

/** Romsdalen. Somewhere with mountains, so an empty map is not an empty map. */
const CENTER: [number, number] = [62.63, 7.896];

/** Deeper than any layer has tiles for: past its maxNativeZoom each one is
 *  scaled up rather than fetched. Every TileLayer needs it too, or Leaflet
 *  hides the layer beyond its own default maxZoom of 18. */
const MAX_ZOOM = 20;

export type MapApi = {
  zoomIn: () => void;
  zoomOut: () => void;
  locateUser: () => void;
};

type DraggableMarkerProps = {
  position: LatLng;
  icon: DivIcon;
  onPositionChange: (position: LatLng) => void;
};

const DraggableMarker = ({ position, icon, onPositionChange }: DraggableMarkerProps) => (
  <Marker
    position={[position.lat, position.lng]}
    icon={icon}
    draggable
    eventHandlers={{
      dragend: (e) => {
        const { lat, lng } = (e.target as LeafletMarker).getLatLng();
        onPositionChange({ lat, lng });
      },
    }}
    pane="markers"
  />
);

type MapViewProps = {
  basemap: BasemapId;
  onBasemapChange: (id: BasemapId) => void;
  overlays: Record<OverlayId, boolean>;
  onToggleOverlay: (id: OverlayId) => void;
  overlayOpacity: Record<OverlayId, number>;
  onOverlayOpacityChange: (id: OverlayId, opacity: number) => void;
  panelOpen: boolean;
  /** The drawer's live width, so what the map zooms to stays clear of it. */
  panelWidth: number;
  onOpenPanel: () => void;
  addMode: AddMode;
  /** Start drawing has been pressed, so map clicks add points. */
  isDrawing: boolean;
  /** A Route's line open for editing, or null when none is. It takes the
   *  map over a line being drawn, which waits underneath meanwhile. */
  editDraft: readonly LatLng[] | null;
  onEditDraftChange: (points: LatLng[]) => void;
  /** The line being drawn, in drawing order. */
  draft: readonly LatLng[];
  onDraftChange: (points: LatLng[]) => void;
  /** The points Generate routes through, start first and end last. */
  waypoints: readonly LatLng[];
  /** Whether the next map click picks one of them. */
  picking: boolean;
  onPickPoint: (point: LatLng) => void;
  onCancelPick: () => void;
  onMovePoint: (index: number, point: LatLng) => void;
  routes: readonly Route[];
  selectedId: string | null;
  onSelectRoute: (id: string) => void;
  focus: MapFocus | null;
  onDropFiles: (files: File[]) => void;
  corridor: CorridorImage | null;
  showCorridor: boolean;
  corridorOpacity: number;
  onCruxClick: (routeId: string, cruxId: string) => void;
  /** The line a Crux is being placed on, while Add crux is pressed. */
  placeCruxOn: LineString | null;
  pendingCrux: LatLng | null;
  /** The line the pending Crux would colour, previewed while its form is open. */
  pendingStretch: { positions: LatLngTuple[]; color: string } | null;
  onPlaceCrux: (spot: { position: LatLng; distance_m: number }) => void;
  onCancelPlaceCrux: () => void;
  /** A Crux's extent being edited: the line, where its ends are now, and
   *  the colour of the handles. */
  extentEdit: { line: LineString; extent: Extent; color: string } | null;
  onExtentChange: (extent: Extent) => void;
  onCancelExtent: () => void;
  /** The Selected route's suggestions on show, and the line they are for. */
  suggestions: { line: LineString; items: readonly RouteSuggestion[] } | null;
  activeSuggestionId: string | null;
  onSuggestionClick: (id: string) => void;
  onAcceptSuggestion: (id: string) => void;
  onRejectSuggestion: (id: string) => void;
  /** The open suggestion's popup was closed on the map. */
  onCloseSuggestion: (id: string) => void;
};

/** Covers the map while files are dragged over it, and takes the drop.
 *
 * Only there while dragging, and covering everything, so its own dragleave
 * fires only when the files really leave - not every time the pointer
 * crosses from one map element to the next. */
const DropOverlay = ({ onDrop, onLeave }: { onDrop: (files: File[]) => void; onLeave: () => void }) => (
  <Box
    onDragOver={(e) => e.preventDefault()}
    onDragLeave={onLeave}
    onDrop={(e) => {
      // Without this the browser opens the file in place of the app.
      e.preventDefault();
      onLeave();
      const files = Array.from(e.dataTransfer.files);
      if (files.length > 0) onDrop(files);
    }}
    sx={{
      position: "absolute",
      inset: 0,
      zIndex: 1250,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: "rgba(54,126,152,0.25)",
      border: `3px dashed ${COLORS.teal}`,
      boxSizing: "border-box",
    }}
  >
    <Typography
      sx={{
        pointerEvents: "none",
        color: "white",
        fontSize: 18,
        fontWeight: 600,
        px: 2,
        py: 1,
        borderRadius: 2,
        backgroundColor: COLORS.panel,
      }}
    >
      Drop GPX/GeoJSON files to add them as routes
    </Typography>
  </Box>
);

const MapView = ({
  basemap,
  onBasemapChange,
  overlays,
  onToggleOverlay,
  overlayOpacity,
  onOverlayOpacityChange,
  panelOpen,
  panelWidth,
  onOpenPanel,
  addMode,
  isDrawing,
  editDraft,
  onEditDraftChange,
  draft,
  onDraftChange,
  waypoints,
  picking,
  onPickPoint,
  onCancelPick,
  onMovePoint,
  routes,
  selectedId,
  onSelectRoute,
  focus,
  onDropFiles,
  corridor,
  showCorridor,
  corridorOpacity,
  onCruxClick,
  placeCruxOn,
  pendingCrux,
  pendingStretch,
  onPlaceCrux,
  onCancelPlaceCrux,
  extentEdit,
  onExtentChange,
  onCancelExtent,
  suggestions,
  activeSuggestionId,
  onSuggestionClick,
  onAcceptSuggestion,
  onRejectSuggestion,
  onCloseSuggestion,
}: MapViewProps) => {
  const bm = useMemo(() => getBasemap(basemap), [basemap]);
  const mapApiRef = useRef<MapApi | null>(null);
  const [dragging, setDragging] = useState(false);

  // On a phone the drawer is a modal over the map, closed to look at it, so
  // there is nothing to keep clear of.
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const leftInset = panelOpen && !isMobile ? panelWidth : 0;

  // Drawing only while the drawer can say so - except on a phone, where the
  // drawer covers the map and has to be closed to draw at all.
  // Placing a Crux takes the clicks for itself while it is on.
  const placing = placeCruxOn !== null;
  // Paused while a point is picked or a Crux placed: the click is theirs.
  const editingLine = editDraft !== null && !placing && !picking;
  const drawing =
    !editingLine && addMode === "draw" && isDrawing && (panelOpen || isMobile) && !placing;
  // The points only mean something to the router.
  const showPoints = addMode === "generate";

  return (
    <Box
      sx={{ height: "100dvh", width: "100vw", position: "relative" }}
      onDragEnter={(e) => {
        // Files only: dragging a marker or the map itself is not an upload.
        if (e.dataTransfer.types.includes("Files")) setDragging(true);
      }}
    >
      <MapContainer
        center={CENTER}
        zoom={11}
        minZoom={5}
        maxZoom={MAX_ZOOM}
        zoomControl={false}
        zoomAnimation={false}
        fadeAnimation={false}
        markerZoomAnimation={false}
        style={{ height: "100%", width: "100vw" }}
      >
        {/* Explicit panes so the stack is fixed: basemap, overlays, the
            routes, then the markers you drag on top of all of it. */}
        <Pane name="basemap" style={{ zIndex: 200 }}>
          <TileLayer
            url={bm.url}
            attribution={bm.attribution}
            maxZoom={MAX_ZOOM}
            maxNativeZoom={bm.maxNativeZoom}
          />
        </Pane>

        <Pane name="overlays" style={{ zIndex: 300 }}>
          {OVERLAYS.filter((o) => overlays[o.id] && !o.tileIndexUrl).map((o) => (
            <TileLayer
              key={o.id}
              url={o.tileUrl}
              maxZoom={MAX_ZOOM}
              maxNativeZoom={o.maxNativeZoom}
              opacity={overlayOpacity[o.id] ?? o.opacityDefault}
              pane="overlays"
            />
          ))}
        </Pane>

        {/* The tour corridors, over the slope layers rather than among them:
            in one pane the last layer switched on would go on top. Still
            under the routed corridor, which is the one being worked on. */}
        <Pane name="tourCorridors" style={{ zIndex: 320, pointerEvents: "none" }}>
          {OVERLAYS.filter((o) => overlays[o.id] && o.tileIndexUrl).map((o) => (
            <IndexedTileLayer
              key={o.id}
              url={o.tileUrl}
              indexUrl={o.tileIndexUrl!}
              maxZoom={MAX_ZOOM}
              maxNativeZoom={o.maxNativeZoom}
              opacity={overlayOpacity[o.id] ?? o.opacityDefault}
              pane="tourCorridors"
            />
          ))}
        </Pane>

        {/* Under the routes, so the line stays readable on top of its band. */}
        <Pane name="corridor" style={{ zIndex: 350, pointerEvents: "none" }}>
          {corridor && showCorridor && (
            <CorridorOverlay
              key={corridor.png_path}
              corridor={corridor}
              opacity={corridorOpacity}
            />
          )}
        </Pane>

        <Pane name="route" style={{ zIndex: 450 }}>
          <RouteLines
            routes={routes}
            selectedId={selectedId}
            clickTaken={picking || drawing || editingLine || placing}
            onSelect={onSelectRoute}
          />
        </Pane>

        {/* Over the line they would change, under its Crux markers. */}
        <Pane name="suggestions" style={{ zIndex: 470 }}>
          {suggestions && (
            <SuggestionLines
              line={suggestions.line}
              suggestions={suggestions.items}
              activeId={activeSuggestionId}
              onSelect={onSuggestionClick}
              onAccept={onAcceptSuggestion}
              onReject={onRejectSuggestion}
              onClose={onCloseSuggestion}
            />
          )}
        </Pane>

        {/* Above the routes, so a Crux is never under its own red line, and
            below the start and end you drag. */}
        <Pane name="cruxes" style={{ zIndex: 500 }} />
        <CruxMarkers
          routes={routes}
          selectedId={selectedId}
          focus={focus}
          onCruxClick={onCruxClick}
        />

        <Pane name="markers" style={{ zIndex: 600, pointerEvents: "auto" }} />

        {showPoints &&
          waypoints.map((point, i) => (
            <DraggableMarker
              // By place: a point keeps its marker while it is dragged, and
              // one added in between renumbers the rest anyway.
              key={i}
              position={point}
              icon={
                i === 0 ? startIcon : i === waypoints.length - 1 ? endIcon : waypointIcon(i)
              }
              onPositionChange={(moved) => onMovePoint(i, moved)}
            />
          ))}

        <MapClickPicker active={picking} onPick={onPickPoint} onCancel={onCancelPick} />

        <DrawLayer
          active={drawing || editingLine}
          points={editingLine ? editDraft : draft}
          onChange={editingLine ? onEditDraftChange : onDraftChange}
        />

        <CruxPlacer
          line={placeCruxOn}
          pending={pendingCrux}
          stretch={pendingStretch}
          onPlace={onPlaceCrux}
          onCancel={onCancelPlaceCrux}
        />

        <ExtentEditor
          line={extentEdit?.line ?? null}
          extent={extentEdit?.extent ?? null}
          color={extentEdit?.color ?? "white"}
          onChange={onExtentChange}
          onCancel={onCancelExtent}
        />

        <MapController
          onReady={(api) => {
            mapApiRef.current = api;
          }}
        />
        <FocusController focus={focus} leftInset={leftInset} />

        <ScaleBar position="bottomleft" />
        <CursorCoords />
      </MapContainer>

      <RoutingButton onClick={onOpenPanel} hidden={panelOpen} />

      {dragging && <DropOverlay onDrop={onDropFiles} onLeave={() => setDragging(false)} />}

      <Box
        sx={{
          position: "fixed",
          top: { xs: 10, sm: 12, md: 16, xl: 22 },
          right: { xs: 8, sm: 12, md: 16, xl: 22 },
          zIndex: 1300,
          display: "flex",
          flexDirection: "column",
          gap: { xs: 1, sm: 1, xl: 1.2 },
          // The column is wider than the buttons in it, and the gaps between
          // them are holes you should still be able to drag the map through.
          pointerEvents: "none",
          "& > *": { pointerEvents: "auto" },
        }}
      >
        <LayerControl
          basemap={basemap}
          onBasemapChange={onBasemapChange}
          overlays={overlays}
          onToggleOverlay={onToggleOverlay}
          overlayOpacity={overlayOpacity}
          onOverlayOpacityChange={onOverlayOpacityChange}
        />
        <MapActions
          onLocate={() => mapApiRef.current?.locateUser()}
          onZoomIn={() => mapApiRef.current?.zoomIn()}
          onZoomOut={() => mapApiRef.current?.zoomOut()}
        />
      </Box>
    </Box>
  );
};

export default MapView;
