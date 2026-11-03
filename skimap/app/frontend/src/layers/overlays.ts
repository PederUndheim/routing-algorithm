import slopeThumb from "../assets/overlays/slope.png";
import runoutThumb from "../assets/overlays/runout.png";
import coloredCorridorsThumb from "../assets/overlays/colored_corridors.png";
import hazardZoneCorridorsThumb from "../assets/overlays/hazard_zone_corridors.png";

/** NVE's steepness tiles - the same two the cost surface is built to agree
 *  with, so they are the quickest way to see whether a route makes sense -
 *  and the reviewed tours' corridors, in the exposure class each one got,
 *  on either of two palettes. */
export type OverlayId = "slope" | "slope_runout" | "colored_corridors" | "hazard_zone_corridors";

export type OverlayDef = {
  id: OverlayId;
  label: string;
  /** Two views of the same thing, so only one layer of a group is on at once. */
  group: "slope" | "corridors";
  tileUrl: string;
  /** The deepest zoom the service has tiles for. NVE's capabilities list
   *  levels to 19, but past this it answers 400; Leaflet scales these up. */
  maxNativeZoom: number;
  opacityDefault: number;
  onByDefault: boolean;
  thumbUrl: string;
  /** For a layer that covers a little of a large area: a JSON list of the
   *  tiles that exist, so only those are fetched (see IndexedTileLayer). */
  tileIndexUrl?: string;
};

const NVE = "https://gis3.nve.no/arcgis/rest/services/wmts";

/** Static tiles shipped with the app, written by `python -m app.corridor_tiles`
 *  from data/colored_corridors. BASE_URL, because Pages serves the site
 *  under the repo name. */
const COLORED_CORRIDORS = `${import.meta.env.BASE_URL}colored_corridors`;
const HAZARD_ZONE_CORRIDORS = `${import.meta.env.BASE_URL}hazard_zone_corridors`;

export const OVERLAYS: OverlayDef[] = [
  {
    id: "slope",
    label: "Slope",
    group: "slope",
    tileUrl: `${NVE}/Bratthet_2024/MapServer/WMTS/tile/1.0.0/wmts_Bratthet_2024/default/GoogleMapsCompatible/{z}/{y}/{x}.png`,
    maxNativeZoom: 16,
    opacityDefault: 0.35,
    onByDefault: true,
    thumbUrl: slopeThumb,
  },
  {
    id: "slope_runout",
    label: "Slope and runout",
    group: "slope",
    tileUrl: `${NVE}/Bratthet_med_utlop_2024/MapServer/WMTS/tile/1.0.0/wmts_Bratthet_med_utlop_2024/default/GoogleMapsCompatible/{z}/{y}/{x}.png`,
    maxNativeZoom: 16,
    opacityDefault: 0.38,
    onByDefault: false,
    thumbUrl: runoutThumb,
  },
  {
    id: "colored_corridors",
    label: "Corridors",
    group: "corridors",
    tileUrl: `${COLORED_CORRIDORS}/{z}/{x}/{y}.png`,
    maxNativeZoom: 12,
    opacityDefault: 0.5,
    onByDefault: false,
    thumbUrl: coloredCorridorsThumb,
    tileIndexUrl: `${COLORED_CORRIDORS}/index.json`,
  },
  {
    id: "hazard_zone_corridors",
    label: "Hazard zone corridors",
    group: "corridors",
    tileUrl: `${HAZARD_ZONE_CORRIDORS}/{z}/{x}/{y}.png`,
    maxNativeZoom: 12,
    opacityDefault: 0.6,
    onByDefault: false,
    thumbUrl: hazardZoneCorridorsThumb,
    tileIndexUrl: `${HAZARD_ZONE_CORRIDORS}/index.json`,
  },
];

/** Both derived from OVERLAYS, so adding a layer above is the only edit. */
export const DEFAULT_OVERLAYS = OVERLAYS.reduce(
  (acc, o) => ({ ...acc, [o.id]: o.onByDefault }),
  {} as Record<OverlayId, boolean>
);

export const DEFAULT_OPACITY = OVERLAYS.reduce(
  (acc, o) => ({ ...acc, [o.id]: o.opacityDefault }),
  {} as Record<OverlayId, number>
);

/** `id` flipped. Switching it on switches off the rest of its group; switching
 *  it off leaves the group with nothing on, which is allowed. */
export const toggleOverlay = (
  overlays: Record<OverlayId, boolean>,
  id: OverlayId
): Record<OverlayId, boolean> => {
  const on = !overlays[id];
  const group = OVERLAYS.find((o) => o.id === id)?.group;
  return OVERLAYS.reduce(
    (acc, o) => (on && o.id !== id && o.group === group ? { ...acc, [o.id]: false } : acc),
    { ...overlays, [id]: on }
  );
};
