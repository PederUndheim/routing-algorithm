import { useEffect, useState } from "react";
import L from "leaflet";
import type { Coords, DoneCallback, TileLayerOptions } from "leaflet";
import { useMap } from "react-leaflet";

/** What app/corridor_tiles.py writes beside the tiles: every one that
 *  exists, as "x/y" per zoom. */
type TileIndex = { tiles: Record<string, string[]> };

/** A TileLayer that asks only for the tiles its index lists.
 *
 *  Made for the colored corridors: a thin scatter of bands over the whole
 *  country, so nearly every tile in view does not exist. An ordinary
 *  TileLayer would request each one anyway and get a 404 back - or, from the
 *  dev server, index.html - per tile. Here a missing tile is an empty div,
 *  finished at once.
 */
class IndexedLayer extends L.TileLayer {
  private present: Set<string>;

  constructor(url: string, present: Set<string>, options: TileLayerOptions) {
    super(url, options);
    this.present = present;
  }

  createTile(coords: Coords, done: DoneCallback): HTMLElement {
    if (this.present.has(`${coords.z}/${coords.x}/${coords.y}`)) {
      return super.createTile(coords, done);
    }
    const empty = document.createElement("div");
    // Async, as an image's load would be: GridLayer has not filed the tile
    // under its key until createTile returns.
    setTimeout(() => done(undefined, empty), 0);
    return empty;
  }
}

/** One fetch per index for the life of the page, however often the layer
 *  is toggled. */
const indexes = new Map<string, Promise<Set<string>>>();

const loadIndex = (url: string) => {
  let index = indexes.get(url);
  if (!index) {
    index = fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`${url}: ${r.status}`);
        return r.json() as Promise<TileIndex>;
      })
      .then(({ tiles }) =>
        new Set(Object.entries(tiles).flatMap(([z, xy]) => xy.map((t) => `${z}/${t}`)))
      );
    // A failed fetch is not cached, so turning the layer off and on retries.
    index.catch(() => indexes.delete(url));
    indexes.set(url, index);
  }
  return index;
};

type IndexedTileLayerProps = {
  url: string;
  indexUrl: string;
  opacity: number;
  pane: string;
  maxZoom: number;
  maxNativeZoom: number;
};

const IndexedTileLayer = ({ url, indexUrl, opacity, pane, maxZoom, maxNativeZoom }: IndexedTileLayerProps) => {
  const map = useMap();
  const [layer, setLayer] = useState<IndexedLayer | null>(null);

  useEffect(() => {
    let cancelled = false;
    let added: IndexedLayer | null = null;
    loadIndex(indexUrl).then(
      (present) => {
        if (cancelled) return;
        added = new IndexedLayer(url, present, { pane, maxZoom, maxNativeZoom, opacity });
        added.addTo(map);
        setLayer(added);
      },
      (error) => console.error("Could not load the tile index", error)
    );
    return () => {
      cancelled = true;
      added?.remove();
      setLayer(null);
    };
    // Opacity is applied below, not by rebuilding the layer.
  }, [map, url, indexUrl, pane, maxZoom, maxNativeZoom]);

  useEffect(() => {
    layer?.setOpacity(opacity);
  }, [layer, opacity]);

  return null;
};

export default IndexedTileLayer;
