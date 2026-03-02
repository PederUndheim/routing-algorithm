import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";

type Bounds = { west: number; south: number; east: number; north: number };

type Props = {
  pngUrl: string | null;
  bounds: Bounds | null;
  opacity?: number;
};

export default function CorridorOverlay({ pngUrl, bounds, opacity }: Props) {
  const map = useMap();
  const layerRef = useRef<L.ImageOverlay | null>(null);

  useEffect(() => {
    // remove old overlay
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    if (!pngUrl || !bounds) return;

    const url = pngUrl.includes("?")
      ? `${pngUrl}&t=${Date.now()}`
      : `${pngUrl}?t=${Date.now()}`;

    const leafletBounds: L.LatLngBoundsExpression = [
      [bounds.south, bounds.west],
      [bounds.north, bounds.east],
    ];

    const overlay = L.imageOverlay(url, leafletBounds, {
      opacity,
      interactive: false,
      pane: "corridor",
    });
    overlay.addTo(map);
    layerRef.current = overlay;

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [pngUrl, bounds, opacity, map]);

  return null;
}
