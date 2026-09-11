import { useEffect } from "react";
import { useMap } from "react-leaflet";

import type { MapApi } from "./MapView";

/** Hands the Leaflet map's imperative bits back out to the buttons that live
 *  outside the MapContainer, where the `useMap` hook cannot reach. */
const MapController = ({ onReady }: { onReady: (api: MapApi) => void }) => {
  const map = useMap();

  useEffect(() => {
    onReady({
      zoomIn: () => map.zoomIn(),
      zoomOut: () => map.zoomOut(),
      locateUser: () => map.locate({ setView: true, maxZoom: 16 }),
    });
  }, [map, onReady]);

  return null;
};

export default MapController;
