import { useMemo, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  Pane,
  WMSTileLayer,
  Marker,
  GeoJSON,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";

import Box from "@mui/material/Box";

import type { BasemapId } from "../layers/basemaps";
import type { OverlayId } from "../layers/overlays";
import type { FeatureCollection } from "geojson";
import type { UserGeoJsonLayer, LatLng, PickMode } from "../types/mapTypes";

import { getBasemap } from "../layers/basemaps";
import { OVERLAYS } from "../layers/overlays";
import { startIcon, endIcon, createStopIcon } from "../ui/StartAndEndIcons";

import MapController from "./MapController";
import BasemapControl from "./BasemapControl";
import MapActions from "./MapActions";
import RoutingButton from "../ui/RoutingButton";
import MapClickPicker from "../ui/MapClickPicker";
import ScaleBar from "../ui/ScaleBar";
import CursorCoords from "../ui/CursorCoords";
import CorridorOverlay from "./CorridorOverlay";

const center: [number, number] = [62.63, 7.896];

export type MapApi = {
  zoomIn: () => void;
  zoomOut: () => void;
  flyToCenter: () => void;
  locateUser: () => void;
};

type DraggableMarkerProps = {
  position: LatLng;
  icon: L.DivIcon;
  onPositionChange: (position: LatLng) => void;
  pane?: string;
};

const DraggableMarker = ({
  position,
  icon,
  onPositionChange,
  pane,
}: DraggableMarkerProps) => {
  return (
    <Marker
      position={[position.lat, position.lng]}
      icon={icon}
      draggable
      eventHandlers={{
        dragend: (e) => {
          const marker = e.target as L.Marker;
          const latLng = marker.getLatLng();
          onPositionChange({ lat: latLng.lat, lng: latLng.lng });
        },
      }}
      pane={pane}
    />
  );
};

type MapViewProps = {
  basemap: BasemapId;
  onBasemapChange: (id: BasemapId) => void;

  overlays: Record<OverlayId, boolean>;
  onToggleOverlay: (id: OverlayId) => void;

  overlayOpacity: Record<OverlayId, number>;
  onOverlayOpacityChange: (id: OverlayId, opacity: number) => void;

  onMapReady: (api: MapApi) => void;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  onCloseSidebar: () => void;

  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  startPoint: LatLng | null;
  endPoint: LatLng | null;
  stopPoints: LatLng[];
  stopPickIndex: number | null;
  onStartPointChange: (point: LatLng | null) => void;
  onEndPointChange: (point: LatLng | null) => void;
  onStopPointChange: (point: LatLng, index: number | null) => void;
  routeGeoJson?: FeatureCollection | null;
  showCorridor: boolean;
  corridorPngUrl?: string | null;
  corridorBounds?: {
    west: number;
    south: number;
    east: number;
    north: number;
  } | null;
  userGeoJsonLayers: UserGeoJsonLayer[];
  onAddGeoJson: (name: string, data: FeatureCollection) => void;
  onToggleGeoJson: (id: string) => void;
  onRemoveGeoJson: (id: string) => void;
  geoJsonVisible: boolean;
  onToggleGeoJsonVisible: () => void;
};

const MapView = ({
  basemap,
  onBasemapChange,
  overlays,
  onToggleOverlay,
  overlayOpacity,
  onOverlayOpacityChange,
  onMapReady,
  sidebarOpen,
  onToggleSidebar,
  pickMode,
  onPickModeChange,
  startPoint,
  endPoint,
  stopPoints,
  stopPickIndex,
  onStartPointChange,
  onEndPointChange,
  onStopPointChange,
  routeGeoJson,
  showCorridor,
  corridorPngUrl,
  corridorBounds,
  userGeoJsonLayers,
  onAddGeoJson,
  onToggleGeoJson,
  onRemoveGeoJson,
  geoJsonVisible,
  onToggleGeoJsonVisible,
}: MapViewProps) => {
  const bm = useMemo(() => getBasemap(basemap), [basemap]);
  const mapApiRef = useRef<MapApi | null>(null);

  return (
    <Box sx={{ height: "100dvh", width: "100vw", position: "relative" }}>
      <MapContainer
        center={center}
        zoom={11}
        maxZoom={18}
        minZoom={5}
        zoomControl={false}
        zoomAnimation={false}
        fadeAnimation={false}
        markerZoomAnimation={false}
        style={{ height: "100%", width: "100vw" }}
      >
        <Pane name="basemap" style={{ zIndex: 200 }}>
          <TileLayer
            url={bm.url}
            attribution={bm.attribution}
          />
        </Pane>

        <Pane name="overlays" style={{ zIndex: 300 }}>
          {OVERLAYS.map((o) => {
            if (!overlays[o.id]) return null;

            const opacity = overlayOpacity[o.id] ?? o.opacityDefault;

            if (o.type === "wms") {
              return (
                <WMSTileLayer
                  key={o.id}
                  url={o.wmsUrl}
                  layers={o.layers}
                  opacity={opacity}
                  transparent
                  format="image/png"
                />
              );
            }

            if (o.type === "geojson") {
              return (
                <GeoJSON
                  key={o.id}
                  data={o.data}
                  style={() => ({
                    weight: 3,
                    opacity: opacity,
                    color: "#367E98",
                    fillColor: "transparent",
                  })}
                />
              );
            }
          })}
        </Pane>

        <Pane name="corridor" style={{ zIndex: 350, pointerEvents: "none" }} />

        {geoJsonVisible &&
          userGeoJsonLayers?.some((layer) => layer.visible) && (
            <Pane name="user-geojson" style={{ zIndex: 400 }}>
              {userGeoJsonLayers
                .filter((layer) => layer.visible)
                .map((layer) => (
                  <GeoJSON
                    key={layer.id}
                    data={layer.data}
                    style={() => ({
                      weight: 4,
                      opacity: 1,
                      color: "#EE7B04",
                      fillColor: "transparent",
                    })}
                  />
                ))}
            </Pane>
          )}

        {routeGeoJson && (
          <Pane name="route" style={{ zIndex: 450 }}>
            <GeoJSON
              data={routeGeoJson}
              style={() => ({
                weight: 6,
                opacity: 1,
                color: "#367E98",
              })}
            />
          </Pane>
        )}

        <Pane name="markers" style={{ zIndex: 600, pointerEvents: "auto" }} />

        {corridorPngUrl && corridorBounds && showCorridor && (
          <CorridorOverlay
            key={corridorPngUrl}
            pngUrl={corridorPngUrl}
            bounds={corridorBounds}
            opacity={0.7}
          />
        )}

        {/* Markers */}
        {startPoint && (
          <DraggableMarker
            position={startPoint}
            icon={startIcon}
            onPositionChange={(p) => onStartPointChange(p)}
            pane="markers"
          />
        )}
        {endPoint && (
          <DraggableMarker
            position={endPoint}
            icon={endIcon}
            onPositionChange={(p) => onEndPointChange(p)}
            pane="markers"
          />
        )}
        {stopPoints.map((stopPoint, index) => (
          <DraggableMarker
            key={`stop-${index}`}
            position={stopPoint}
            icon={createStopIcon(index)}
            onPositionChange={(p) => onStopPointChange(p, index)}
            pane="markers"
          />
        ))}

        {/* Picker layer */}
        <MapClickPicker
          pickMode={pickMode}
          stopPickIndex={stopPickIndex}
          onPickModeChange={onPickModeChange}
          onStartPointChange={onStartPointChange}
          onEndPointChange={onEndPointChange}
          onStopPointChange={onStopPointChange}
        />

        <MapController
          onReady={(api) => {
            mapApiRef.current = api;
            onMapReady(api);
          }}
        />

        <ScaleBar position="bottomleft" />
        <CursorCoords />
      </MapContainer>

      <RoutingButton onClick={onToggleSidebar} hidden={sidebarOpen} />

      <Box
        sx={{
          position: "fixed",
          top: { xs: 10, sm: 12, md: 16, xl: 22 },
          right: { xs: 8, sm: 12, md: 16, xl: 22 },
          zIndex: 1300,
          display: "flex",
          flexDirection: "column",
          gap: { xs: 1, sm: 1, xl: 1.2 },
          pointerEvents: "none",
        }}
      >
        <Box sx={{ pointerEvents: "auto" }}>
          <BasemapControl
            basemap={basemap}
            onBasemapChange={onBasemapChange}
            overlays={overlays}
            onToggleOverlay={onToggleOverlay}
            overlayOpacity={overlayOpacity}
            onOverlayOpacityChange={onOverlayOpacityChange}
            userGeoJsonLayers={userGeoJsonLayers}
            onAddGeoJson={onAddGeoJson}
            onToggleGeoJson={onToggleGeoJson}
            onRemoveGeoJson={onRemoveGeoJson}
            geoJsonVisible={geoJsonVisible}
            onToggleGeoJsonVisible={onToggleGeoJsonVisible}
          />
        </Box>

        <Box sx={{ pointerEvents: "auto" }}>
          <MapActions
            onLocate={() => mapApiRef.current?.locateUser()}
            onZoomIn={() => mapApiRef.current?.zoomIn()}
            onZoomOut={() => mapApiRef.current?.zoomOut()}
          />
        </Box>
      </Box>
    </Box>
  );
};
export default MapView;

// Fargekart (topo)
// Gråtonekart (topograatone)
// Turkart (toporaster)
// Sjøkart (sjokartraster)

// Web mercator - EPSG:3857 (webmercator)
// UTM sone 32 - EPSG:25832 (utm32n)
// UTM sone 33 - EPSG:25833 (utm33n)
// UTM sone 35 - EPSG:25835 (utm35n)
