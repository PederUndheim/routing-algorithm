import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { BASEMAPS, STEEPNESS, type BasemapId, type SteepnessId } from "./layers";
import { corridorImageUrl, trackIndexUrl, trackTileUrl } from "./data";

/** A TileLayer that asks only for the tiles its index lists - the track
 *  tiles exist only near corridors, so most tiles in view do not. Same idea
 *  as the main app's IndexedTileLayer. */
class IndexedLayer extends L.TileLayer {
  constructor(url: string, private present: Set<string>, options: L.TileLayerOptions) {
    super(url, options);
  }

  createTile(coords: L.Coords, done: L.DoneCallback): HTMLElement {
    if (this.present.has(`${coords.z}/${coords.x}/${coords.y}`)) {
      return super.createTile(coords, done);
    }
    const empty = document.createElement("div");
    setTimeout(() => done(undefined, empty), 0);
    return empty;
  }
}

type TrackIndex = { version: number; present: Set<string> };
let trackIndex: Promise<TrackIndex> | null = null;
const loadTrackIndex = (code: string) => {
  trackIndex ??= fetch(trackIndexUrl(code))
    .then((r) => {
      if (!r.ok) throw new Error(`spordata: ${r.status}`);
      return r.json();
    })
    .then(({ version, tiles }: { version?: number; tiles: Record<string, string[]> }) => ({
      version: version ?? 0,
      present: new Set(Object.entries(tiles).flatMap(([z, xy]) => xy.map((t) => `${z}/${t}`))),
    }));
  // A failed fetch is not kept, so toggling the layer again retries.
  trackIndex.catch(() => (trackIndex = null));
  return trackIndex;
};

// As the corridor review drew it. The PNG carries its own alpha ramp, fading
// to nothing at the edge of the band; this is on top of that.
const CORRIDOR_OPACITY = 0.5;

type Props = {
  code: string;
  basemap: BasemapId;
  steepness: SteepnessId | null;
  tracks: boolean;
  opacity: number;
  corridorId: number | null;
  /** The corridor image's bounds: where it goes, and what to zoom to. */
  bbox: [number, number, number, number] | null;
};

export function MapView({ code, basemap, steepness, tracks, opacity, corridorId, bbox }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const baseLayer = useRef<L.TileLayer | null>(null);
  const steepLayer = useRef<L.TileLayer | null>(null);
  const trackLayer = useRef<L.TileLayer | null>(null);
  const corridorLayer = useRef<L.ImageOverlay | null>(null);

  useEffect(() => {
    const m = L.map(host.current!, {
      zoomControl: false, minZoom: 5, maxZoom: 17, zoomSnap: 0.25, keyboard: false,
    }).setView([65, 14], 5);
    m.createPane("steepness").style.zIndex = "350";
    // Tracks over the corridor, as in the review: whether the band follows
    // them is much of what there is to judge.
    m.createPane("corridor").style.zIndex = "400";
    m.createPane("tracks").style.zIndex = "420";
    // Both bottom left; a bottom corner stacks the last-added on top, so the
    // zoom buttons sit above the scale bar.
    L.control.scale({ imperial: false }).addTo(m);
    L.control.zoom({ position: "bottomleft", zoomInTitle: "Zoom inn", zoomOutTitle: "Zoom ut" }).addTo(m);
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const def = BASEMAPS[basemap];
    baseLayer.current?.remove();
    baseLayer.current = L.tileLayer(def.url, {
      maxNativeZoom: def.maxNativeZoom, maxZoom: 17, attribution: def.attribution,
    }).addTo(map.current!);
  }, [basemap]);

  useEffect(() => {
    steepLayer.current?.remove();
    steepLayer.current = null;
    if (!steepness) return;
    const def = STEEPNESS[steepness];
    steepLayer.current = L.tileLayer(def.url, {
      pane: "steepness", maxNativeZoom: def.maxNativeZoom, maxZoom: 17,
      attribution: def.attribution, opacity,
    }).addTo(map.current!);
    // opacity is applied by its own effect; recreating on every slider move
    // would reload every tile.
  }, [steepness]);

  useEffect(() => {
    let cancelled = false;
    trackLayer.current?.remove();
    trackLayer.current = null;
    if (!tracks) return;
    loadTrackIndex(code).then(({ version, present }) => {
      if (cancelled || !map.current) return;
      trackLayer.current = new IndexedLayer(trackTileUrl(code, version), present, {
        pane: "tracks", maxNativeZoom: 13, maxZoom: 17, minZoom: 9,
      }).addTo(map.current);
    }, () => undefined);
    return () => {
      cancelled = true;
    };
  }, [tracks, code]);

  useEffect(() => {
    steepLayer.current?.setOpacity(opacity);
  }, [opacity, steepness]);

  useEffect(() => {
    corridorLayer.current?.remove();
    corridorLayer.current = null;
    if (corridorId === null || !bbox) return;
    const [w, s, e, n] = bbox;
    corridorLayer.current = L.imageOverlay(corridorImageUrl(corridorId), [[s, w], [n, e]], {
      pane: "corridor", opacity: CORRIDOR_OPACITY, interactive: false,
    }).addTo(map.current!);
  }, [corridorId, bbox]);

  useEffect(() => {
    if (!bbox || !map.current) return;
    const [w, s, e, n] = bbox;
    map.current.fitBounds([[s, w], [n, e]], {
      padding: [40, 40], maxZoom: 15, animate: false,
    });
  }, [bbox]);

  return <div ref={host} className="map" />;
}
