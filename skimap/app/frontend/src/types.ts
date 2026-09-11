import type { FeatureCollection } from "geojson";

export type LatLng = { lat: number; lng: number };

/** Which point the next map click sets, or null for an ordinary click. */
export type PickMode = "start" | "end" | null;

/** The corner coordinates a corridor picture is stretched between. */
export type CorridorBounds = {
  west: number;
  south: number;
  east: number;
  north: number;
};

/** The band of near-optimal ground around a route: everywhere you could go
 *  instead without the trip costing much more. Already warped to Web
 *  Mercator by the backend, which is the projection Leaflet stretches an
 *  image overlay in. `png_path` is relative to the API. */
export type Corridor = {
  png_path: string;
  bounds: CorridorBounds;
};

/** What POST /route answers with. Lengths are metres, cost is unitless -
 *  the cumulative cost surface value, comparable only against itself. */
export type RouteResponse = {
  route: FeatureCollection;
  corridor: Corridor;
  length_m: number;
  straight_m: number;
  detour: number;
  cost: number;
  seconds: number;
};
