import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import parseGeoraster from "georaster";
import GeoRasterLayer from "georaster-layer-for-leaflet";

type Props = { tifUrl: string | null; opacity?: number; paneName: string };

export default function CorridorRaster({
  tifUrl,
  opacity = 0.6,
  paneName,
}: Props) {
  const map = useMap();
  const abortRef = useRef<AbortController | null>(null);
  const tokenRef = useRef(0);
  const layerRef = useRef<any>(null);

  const ensurePane = (name: string) => {
    if (map.getPane(name)) return;
    const p = map.createPane(name);
    p.style.zIndex = "600";
    p.style.pointerEvents = "none";
  };

  const clearLayer = () => {
    const l = layerRef.current;
    if (!l) return;
    try {
      l.removeFrom(map);
    } catch {}
    try {
      map.removeLayer(l);
    } catch {}
    layerRef.current = null;
  };

  useEffect(() => {
    const token = ++tokenRef.current;

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    // Always remove the previous layer first
    clearLayer();

    if (!tifUrl) return () => ac.abort();

    (async () => {
      ensurePane(paneName);

      const url = tifUrl.includes("?")
        ? `${tifUrl}&t=${Date.now()}`
        : `${tifUrl}?t=${Date.now()}`;

      const resp = await fetch(url, { cache: "no-store", signal: ac.signal });
      if (!resp.ok) throw new Error(`Failed to fetch tif: ${resp.status}`);

      const buf = await resp.arrayBuffer();
      const georaster = await parseGeoraster(buf);

      if (tokenRef.current !== token) return;

      const layer = new GeoRasterLayer({
        georaster,
        pane: paneName,
        opacity,
        resampleMethod: "nearest",
        updateWhenZooming: true,
        updateWhenIdle: true,
        resolution: 128,
        keepBuffer: 0,
        pixelValuesToColorFn: (vals: any[]) => {
          const v = vals?.[0];
          if (v == null || Number.isNaN(v) || v <= -9999) return null;
          return v > 0.95 ? "#367E98" : null;
        },
      });

      layerRef.current = layer;
      layer.addTo(map);

      // Public API redraw (don’t touch _tiles/_levels/_panes)
      try {
        layer.redraw?.();
      } catch {}
    })().catch((e) => {
      if (e?.name === "AbortError") return;
      clearLayer();
    });

    return () => {
      ac.abort();
      if (tokenRef.current === token) clearLayer();
    };
  }, [tifUrl, paneName, opacity, map]);

  return null;
}
