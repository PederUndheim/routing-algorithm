import { useMemo, useRef } from "react";
import { GeoJSON, MapContainer, Marker, Pane, TileLayer } from "react-leaflet";
import type { FeatureCollection } from "geojson";
import type { DivIcon, Marker as LeafletMarker } from "leaflet";

import Box from "@mui/material/Box";

import { getBasemap } from "../layers/basemaps";
import type { BasemapId } from "../layers/basemaps";
import { OVERLAYS } from "../layers/overlays";
import type { OverlayId } from "../layers/overlays";
import type { Corridor, LatLng, PickMode } from "../types";
import { COLORS } from "../theme";

import { endIcon, startIcon } from "../ui/MarkerIcons";
import CursorCoords from "../ui/CursorCoords";
import MapClickPicker from "../ui/MapClickPicker";
import RoutingButton from "../ui/RoutingButton";
import ScaleBar from "../ui/ScaleBar";

import CorridorOverlay from "./CorridorOverlay";
import LayerControl from "./LayerControl";
import MapActions from "./MapActions";
import MapController from "./MapController";

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
  onOpenPanel: () => void;
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  startPoint: LatLng | null;
  endPoint: LatLng | null;
  onStartPointChange: (point: LatLng) => void;
  onEndPointChange: (point: LatLng) => void;
  routeGeoJson: FeatureCollection | null;
  corridor: Corridor | null;
  showCorridor: boolean;
  corridorOpacity: number;
};

const MapView = ({
  basemap,
  onBasemapChange,
  overlays,
  onToggleOverlay,
  overlayOpacity,
  onOverlayOpacityChange,
  panelOpen,
  onOpenPanel,
  pickMode,
  onPickModeChange,
  startPoint,
  endPoint,
  onStartPointChange,
  onEndPointChange,
  routeGeoJson,
  corridor,
  showCorridor,
  corridorOpacity,
}: MapViewProps) => {
  const bm = useMemo(() => getBasemap(basemap), [basemap]);
  const mapApiRef = useRef<MapApi | null>(null);

  return (
    <Box sx={{ height: "100dvh", width: "100vw", position: "relative" }}>
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
            route, then the markers you drag on top of all of it. */}
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

        {/* Under the route, so the line stays readable on top of its band. */}
        <Pane name="corridor" style={{ zIndex: 350, pointerEvents: "none" }}>
          {corridor && showCorridor && (
            <CorridorOverlay
              key={corridor.png_path}
              corridor={corridor}
              opacity={corridorOpacity}
            />
          )}
        </Pane>

        {routeGeoJson && (
          <Pane name="route" style={{ zIndex: 450 }}>
            {/* Keyed on the data so a new route replaces the old line -
                react-leaflet's GeoJSON does not re-render on prop change. */}
            <GeoJSON
              key={JSON.stringify(routeGeoJson)}
              data={routeGeoJson}
              style={() => ({ weight: 6, opacity: 1, color: COLORS.teal })}
            />
          </Pane>
        )}

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

        <ScaleBar position="bottomleft" />
        <CursorCoords />
      </MapContainer>

      <RoutingButton onClick={onOpenPanel} hidden={panelOpen} />

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
