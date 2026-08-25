import type { FeatureCollection } from "geojson";

export type LatLng = { lat: number; lng: number };
export type PickMode = "start" | "end" | "stop" | null;

export type UserGeoJsonLayer = {
  id: string;
  name: string;
  visible: boolean;
  data: FeatureCollection;
};
