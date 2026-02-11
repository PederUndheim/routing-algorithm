import topoThumb from "../assets/basemaps/topo.png";
import graatoneThumb from "../assets/basemaps/topograatone.png";
import turkartThumb from "../assets/basemaps/toporaster.png";
import sjokartThumb from "../assets/basemaps/sjokartraster.png";

export type BasemapId =
  | "topo"
  | "topograatone"
  | "toporaster"
  | "sjokartraster";

export type BasemapDef = {
  id: BasemapId;
  label: string;
  url: string;
  attribution: string;
  maxZoom?: number;
  thumbUrl: string;
};

const baseUrl = "https://cache.kartverket.no/v1/wmts/1.0.0";

export const BASEMAPS: BasemapDef[] = [
  {
    id: "topo",
    label: "Fargekart",
    url: `${baseUrl}/topo/default/webmercator/{z}/{y}/{x}.png`,
    attribution: "© Kartverket",
    maxZoom: 18,
    thumbUrl: topoThumb,
  },
  {
    id: "topograatone",
    label: "Gråtonekart",
    url: `${baseUrl}/topograatone/default/webmercator/{z}/{y}/{x}.png`,
    attribution: "© Kartverket",
    maxZoom: 18,
    thumbUrl: graatoneThumb,
  },
  {
    id: "toporaster",
    label: "Turkart",
    url: `${baseUrl}/toporaster/default/webmercator/{z}/{y}/{x}.png`,
    attribution: "© Kartverket",
    maxZoom: 18,
    thumbUrl: turkartThumb,
  },
  {
    id: "sjokartraster",
    label: "Sjøkart",
    url: `${baseUrl}/sjokartraster/default/webmercator/{z}/{y}/{x}.png`,
    attribution: "© Kartverket",
    maxZoom: 18,
    thumbUrl: sjokartThumb,
  },
];

export const getBasemap = (id: BasemapId): BasemapDef => {
  const basemap = BASEMAPS.find((b) => b.id === id);
  if (!basemap) return BASEMAPS[0];
  return basemap;
};
