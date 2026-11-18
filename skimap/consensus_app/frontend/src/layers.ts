/** The map's layers: one basemap at a time, and overlays on top. */

import topoThumb from "./assets/topo.jpg";
import satelliteThumb from "./assets/satellite.jpg";
import turkartThumb from "./assets/toporaster.jpg";
import slopeThumb from "./assets/slope.jpg";
import runoutThumb from "./assets/runout.jpg";
import tracksThumb from "./assets/tracks.jpg";

export type BasemapId = "topo" | "satellite" | "turkart";
export type SteepnessId = "bratthet" | "bratthet_utlop";

export type TileDef = {
  label: string;
  url: string;
  /** Deepest zoom the service has tiles for; Leaflet scales up past it. */
  maxNativeZoom: number;
  attribution: string;
  thumb: string;
};

const KARTVERKET = "https://cache.kartverket.no/v1/wmts/1.0.0";
const NVE = "https://gis3.nve.no/arcgis/rest/services/wmts";

/** In button order. */
export const BASEMAPS: Record<BasemapId, TileDef> = {
  topo: {
    label: "Norgeskart",
    url: `${KARTVERKET}/topo/default/webmercator/{z}/{y}/{x}.png`,
    maxNativeZoom: 18,
    attribution: "© Kartverket",
    thumb: topoThumb,
  },
  // Norge i bilder's open cache did not answer when this was built; Esri's
  // imagery is free to view with attribution and covers Norway well.
  satellite: {
    label: "Satellitt",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    maxNativeZoom: 18,
    attribution: "© Esri, Maxar, Earthstar Geographics",
    thumb: satelliteThumb,
  },
  turkart: {
    label: "Turkart",
    url: `${KARTVERKET}/toporaster/default/webmercator/{z}/{y}/{x}.png`,
    maxNativeZoom: 18,
    attribution: "© Kartverket",
    thumb: turkartThumb,
  },
};

/** NVE's steepness maps - the two the cost surface was built to agree with. */
export const STEEPNESS: Record<SteepnessId, TileDef> = {
  bratthet: {
    label: "Bratthet",
    url: `${NVE}/Bratthet_2024/MapServer/WMTS/tile/1.0.0/wmts_Bratthet_2024/default/GoogleMapsCompatible/{z}/{y}/{x}.png`,
    maxNativeZoom: 16,
    attribution: "© NVE",
    thumb: slopeThumb,
  },
  bratthet_utlop: {
    label: "Bratthet m/utløp",
    url: `${NVE}/Bratthet_med_utlop_2024/MapServer/WMTS/tile/1.0.0/wmts_Bratthet_med_utlop_2024/default/GoogleMapsCompatible/{z}/{y}/{x}.png`,
    maxNativeZoom: 16,
    attribution: "© NVE",
    thumb: runoutThumb,
  },
};

export const TRACKS_THUMB = tracksThumb;
