import { useEffect } from "react";
import { useMap, useMapEvents } from "react-leaflet";

import type { LatLng } from "../types";

type MapClickPickerProps = {
  /** Whether map clicks pick a point now. */
  active: boolean;
  onPick: (point: LatLng) => void;
  /** Escape: stop picking, keeping whatever has been picked so far. */
  onCancel: () => void;
};

/** Hands map clicks to `onPick` while picking. What a click does - the
 *  start, the end, one point moved - is the caller's to say. Renders
 *  nothing; it is only here for the events. */
const MapClickPicker = ({ active, onPick, onCancel }: MapClickPickerProps) => {
  const map = useMap();

  useEffect(() => {
    const el = map.getContainer();
    el.style.cursor = active ? "crosshair" : "";
    return () => {
      el.style.cursor = "";
    };
  }, [map, active]);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, onCancel]);

  useMapEvents({
    click: (e) => {
      if (active) onPick({ lat: e.latlng.lat, lng: e.latlng.lng });
    },
  });

  return null;
};

export default MapClickPicker;
