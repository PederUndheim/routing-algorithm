import { useMemo, useRef, useState } from "react";
import { MapContainer, Marker, Pane, TileLayer } from "react-leaflet";
import type { DivIcon, Marker as LeafletMarker } from "leaflet";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";

import { getBasemap } from "../layers/basemaps";
import type { BasemapId } from "../layers/basemaps";
import { OVERLAYS } from "../layers/overlays";
import type { OverlayId } from "../layers/overlays";
import type { Route } from "../routes/routeList";
import type { Corridor, LatLng, MapFocus, PickMode } from "../types";
import { COLORS } from "../theme";

import { endIcon, startIcon } from "../ui/MarkerIcons";
import CursorCoords from "../ui/CursorCoords";
import MapClickPicker from "../ui/MapClickPicker";
import RoutingButton from "../ui/RoutingButton";
import ScaleBar from "../ui/ScaleBar";

import CorridorOverlay from "./CorridorOverlay";
import CruxMarkers from "./CruxMarkers";
import FocusController from "./FocusController";
import LayerControl from "./LayerControl";
import MapActions from "./MapActions";
import MapController from "./MapController";
import RouteLines from "./RouteLines";

/** Romsdalen. Somewhere with mountains, so an empty map is not an empty map. */
const CENTER: [number, number] = [62.63, 7.896];

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
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  startPoint: LatLng | null;
  endPoint: LatLng | null;
  onStartPointChange: (point: LatLng) => void;
  onEndPointChange: (point: LatLng) => void;
  routes: readonly Route[];
  selectedId: string | null;
  onSelectRoute: (id: string) => void;
  focus: MapFocus | null;
  onDropFiles: (files: File[]) => void;
  corridor: Corridor | null;
  showCorridor: boolean;
  corridorOpacity: number;
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
  pickMode,
  onPickModeChange,
  startPoint,
  endPoint,
  onStartPointChange,
  onEndPointChange,
  routes,
  selectedId,
  onSelectRoute,
  focus,
  onDropFiles,
  corridor,
  showCorridor,
  corridorOpacity,
}: MapViewProps) => {
  const bm = useMemo(() => getBasemap(basemap), [basemap]);
  const mapApiRef = useRef<MapApi | null>(null);
  const [dragging, setDragging] = useState(false);

  // On a phone the drawer is a modal over the map, closed to look at it, so
  // there is nothing to keep clear of.
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const leftInset = panelOpen && !isMobile ? panelWidth : 0;

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
        maxZoom={18}
        zoomControl={false}
        zoomAnimation={false}
        fadeAnimation={false}
        markerZoomAnimation={false}
        style={{ height: "100%", width: "100vw" }}
      >
        {/* Explicit panes so the stack is fixed: basemap, overlays, the
            routes, then the markers you drag on top of all of it. */}
        <Pane name="basemap" style={{ zIndex: 200 }}>
          <TileLayer url={bm.url} attribution={bm.attribution} />
        </Pane>

        <Pane name="overlays" style={{ zIndex: 300 }}>
          {OVERLAYS.filter((o) => overlays[o.id]).map((o) => (
            <TileLayer
              key={o.id}
              url={o.tileUrl}
              opacity={overlayOpacity[o.id] ?? o.opacityDefault}
              pane="overlays"
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
            pickMode={pickMode}
            onSelect={onSelectRoute}
          />
        </Pane>

        {/* Above the routes, so a Crux is never under its own red line, and
            below the start and end you drag. */}
        <Pane name="cruxes" style={{ zIndex: 500 }} />
        <CruxMarkers routes={routes} selectedId={selectedId} focus={focus} />

        <Pane name="markers" style={{ zIndex: 600, pointerEvents: "auto" }} />

        {startPoint && (
          <DraggableMarker
            position={startPoint}
            icon={startIcon}
            onPositionChange={onStartPointChange}
          />
        )}
        {endPoint && (
          <DraggableMarker
            position={endPoint}
            icon={endIcon}
            onPositionChange={onEndPointChange}
          />
        )}

        <MapClickPicker
          pickMode={pickMode}
          onPickModeChange={onPickModeChange}
          onStartPointChange={onStartPointChange}
          onEndPointChange={onEndPointChange}
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
