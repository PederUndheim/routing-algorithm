import { useEffect } from "react";
import { useMap, useMapEvents } from "react-leaflet";

import type { LatLng, PickMode } from "../types";

type MapClickPickerProps = {
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  onStartPointChange: (point: LatLng) => void;
  onEndPointChange: (point: LatLng) => void;
};

/** Turns the next map click into whichever point `pickMode` names, then
 *  hands the map back. Renders nothing; it is only here for the events. */
const MapClickPicker = ({
  pickMode,
  onPickModeChange,
  onStartPointChange,
  onEndPointChange,
}: MapClickPickerProps) => {
  const map = useMap();

  useEffect(() => {
    const el = map.getContainer();
    el.style.cursor = pickMode ? "crosshair" : "";
    return () => {
      el.style.cursor = "";
    };
  }, [map, pickMode]);

  useMapEvents({
    click: (e) => {
      if (!pickMode) return;
      const point: LatLng = { lat: e.latlng.lat, lng: e.latlng.lng };
      if (pickMode === "start") onStartPointChange(point);
      else onEndPointChange(point);
      onPickModeChange(null);
    },
  });

  return null;
};

export default MapClickPicker;
