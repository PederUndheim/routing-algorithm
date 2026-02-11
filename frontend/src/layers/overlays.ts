import slopeThumb from "../assets/overlays/slope.png";

export type OverlayId = "slope" | "slope_runout";

export type OverlayDef = {
  id: OverlayId;
  label: string;
  type: "wms";
  wmsUrl: string;
  layers: string;
  opacityDefault: number;
  thumbUrl: string;
};

export const OVERLAYS: OverlayDef[] = [
  {
    id: "slope",
    label: "Slope",
    type: "wms",
    wmsUrl:
      "https://nve.geodataonline.no/arcgis/services/Bratthet/MapServer/WmsServer",
    layers: "Bratthet_snoskred",
    opacityDefault: 0.55,
    thumbUrl: slopeThumb,
  },

  {
    id: "slope_runout",
    label: "Slope with runout",
    type: "wms",
    wmsUrl:
      "https://gis3.nve.no/arcgis/services/wmts/Bratthet_med_utlop_2024/MapServer/WMSServer",
    layers: "9,6,7,8",
    opacityDefault: 0.38,
    thumbUrl: slopeThumb,
  },
];
