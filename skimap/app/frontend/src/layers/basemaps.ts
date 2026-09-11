import topoThumb from "../assets/basemaps/topo.png";
import graatoneThumb from "../assets/basemaps/topograatone.png";
import turkartThumb from "../assets/basemaps/toporaster.png";
import sjokartThumb from "../assets/basemaps/sjokartraster.png";

export type BasemapId = "topo" | "topograatone" | "toporaster" | "sjokartraster";

export type BasemapDef = {
  id: BasemapId;
  label: string;
  url: string;
  attribution: string;
  thumbUrl: string;
};

const KARTVERKET = "https://cache.kartverket.no/v1/wmts/1.0.0";

export const BASEMAPS: BasemapDef[] = [
  {
    id: "topo",
    label: "Fargekart",
    url: `${KARTVERKET}/topo/default/webmercator/{z}/{y}/{x}.png`,
    attribution: "© Kartverket",
    thumbUrl: topoThumb,
  },
  {
    id: "topograatone",
    label: "Gråtonekart",
    url: `${KARTVERKET}/topograatone/default/webmercator/{z}/{y}/{x}.png`,
    attribution: "© Kartverket",
    thumbUrl: graatoneThumb,
  },
  {
    id: "toporaster",
    label: "Turkart",
    url: `${KARTVERKET}/toporaster/default/webmercator/{z}/{y}/{x}.png`,
    attribution: "© Kartverket",
    thumbUrl: turkartThumb,
  },
  {
    id: "sjokartraster",
    label: "Sjøkart",
    url: `${KARTVERKET}/sjokartraster/default/webmercator/{z}/{y}/{x}.png`,
    attribution: "© Kartverket",
    thumbUrl: sjokartThumb,
  },
];

export const getBasemap = (id: BasemapId): BasemapDef =>
  BASEMAPS.find((b) => b.id === id) ?? BASEMAPS[0];

export const DEFAULT_BASEMAP: BasemapId = "topo";
