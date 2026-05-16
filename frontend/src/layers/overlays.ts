import type { FeatureCollection } from "geojson";
import studyAreas from "../assets/json/study_areas_wgs84.json";

const studyAreasGeoJson = studyAreas as FeatureCollection;

import slopeThumb from "../assets/overlays/slope.png";
import runoutThumb from "../assets/overlays/runout.png";
import studyAreasThumb from "../assets/overlays/study_areas.png";

export type OverlayId = "slope" | "slope_runout" | "study_areas";

type OverlayBase = {
  id: OverlayId;
  label: string;
  opacityDefault: number;
  thumbUrl: string;
};

export type WmsOverlay = OverlayBase & {
  type: "wms";
  wmsUrl: string;
  layers: string;
};

export type GeoJsonOverlay = OverlayBase & {
  type: "geojson";
  data: FeatureCollection;
};

export type OverlayDef = WmsOverlay | GeoJsonOverlay;

export const OVERLAYS: OverlayDef[] = [
  {
    id: "study_areas",
    label: "Study areas",
    type: "geojson",
    data: studyAreasGeoJson,
    opacityDefault: 1.0,
    thumbUrl: studyAreasThumb,
  },
  {
    id: "slope",
    label: "Slope",
    type: "wms",
    wmsUrl:
      "https://gis3.nve.no/arcgis/rest/services/wmts/Bratthet_2024/MapServer",
    layers: "Bratthet_snoskred",
    opacityDefault: 0.55,
    thumbUrl: slopeThumb,
  },
  {
    id: "slope_runout",
    label: "Runout",
    type: "wms",
    wmsUrl:
      "https://gis3.nve.no/arcgis/services/wmts/Bratthet_med_utlop_2024/MapServer/WMSServer",
    layers: "9,6,7,8",
    opacityDefault: 0.38,
    thumbUrl: runoutThumb,
  },
];
