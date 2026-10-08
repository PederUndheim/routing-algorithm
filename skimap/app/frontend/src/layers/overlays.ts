import slopeThumb from "../assets/overlays/slope.png";
import runoutThumb from "../assets/overlays/runout.png";

/** NVE's steepness tiles - the same two the cost surface is built to agree
 *  with, so they are the quickest way to see whether a route makes sense. */
export type OverlayId = "slope" | "slope_runout";

export type OverlayDef = {
  id: OverlayId;
  label: string;
  tileUrl: string;
  /** The deepest zoom the service has tiles for. NVE's capabilities list
   *  levels to 19, but past this it answers 400; Leaflet scales these up. */
  maxNativeZoom: number;
  opacityDefault: number;
  onByDefault: boolean;
  thumbUrl: string;
};

const NVE = "https://gis3.nve.no/arcgis/rest/services/wmts";

export const OVERLAYS: OverlayDef[] = [
  {
    id: "slope",
    label: "Slope",
    tileUrl: `${NVE}/Bratthet_2024/MapServer/WMTS/tile/1.0.0/wmts_Bratthet_2024/default/GoogleMapsCompatible/{z}/{y}/{x}.png`,
    maxNativeZoom: 16,
    opacityDefault: 0.35,
    onByDefault: true,
    thumbUrl: slopeThumb,
  },
  {
    id: "slope_runout",
    label: "Slope and runout",
    tileUrl: `${NVE}/Bratthet_med_utlop_2024/MapServer/WMTS/tile/1.0.0/wmts_Bratthet_med_utlop_2024/default/GoogleMapsCompatible/{z}/{y}/{x}.png`,
    maxNativeZoom: 16,
    opacityDefault: 0.38,
    onByDefault: false,
    thumbUrl: runoutThumb,
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
