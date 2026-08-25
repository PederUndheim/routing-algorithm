import { useEffect } from "react";
import { useMap } from "react-leaflet";
import type { MapApi } from "./MapView";

const center: [number, number] = [62.63, 7.896];

type MapControllerProps = {
  onReady: (api: MapApi) => void;
};

const MapController = ({ onReady }: MapControllerProps) => {
  const map = useMap();

  useEffect(() => {
    const api: MapApi = {
      zoomIn: () => map.zoomIn(),
      zoomOut: () => map.zoomOut(),
      flyToCenter: () => map.flyTo(center, map.getZoom()),
      locateUser: () => map.locate({ setView: true, maxZoom: 16 }),
    };
    onReady(api);
  }, [map, onReady]);

  return null;
};

export default MapController;
