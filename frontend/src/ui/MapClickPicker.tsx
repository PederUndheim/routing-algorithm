import { useEffect } from "react";
import { useMap, useMapEvents } from "react-leaflet";
import type { LatLng, PickMode } from "../types/mapTypes";

type MapClickPickerProps = {
  pickMode: PickMode;
  stopPickIndex: number | null;
  onPickModeChange: (mode: PickMode) => void;
  onStartPointChange: (point: LatLng | null) => void;
  onEndPointChange: (point: LatLng | null) => void;
  onStopPointChange: (point: LatLng, index: number | null) => void;
};

const MapClickPicker = ({
  pickMode,
  stopPickIndex,
  onPickModeChange,
  onStartPointChange,
  onEndPointChange,
  onStopPointChange,
}: MapClickPickerProps) => {
  const map = useMap();

  useEffect(() => {
    const el = map.getContainer();
    if (!el) return;

    el.style.cursor = pickMode ? "crosshair" : "";
    return () => {
      el.style.cursor = "";
    };
  }, [map, pickMode]);

  useMapEvents({
    click(e) {
      if (!pickMode) return;
      const point: LatLng = { lat: e.latlng.lat, lng: e.latlng.lng };
      if (pickMode === "start") onStartPointChange(point);
      if (pickMode === "end") onEndPointChange(point);
      if (pickMode === "stop") onStopPointChange(point, stopPickIndex);
      onPickModeChange(null);
    },
  });

  return null;
};

export default MapClickPicker;
