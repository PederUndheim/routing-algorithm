import type { FeatureCollection, LineString } from "geojson";

export type LatLng = { lat: number; lng: number };

/** Which point the next map click sets, or null for an ordinary click. */
export type PickMode = "start" | "end" | null;

/** Somewhere the map should move to: a whole Route, or one Crux with its
 *  popup open. A new object each time, so asking twice still moves it. */
export type MapFocus =
  | { kind: "route"; line: LineString }
  | { kind: "crux"; routeId: string; number: number; position: LatLng };

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

/** A Danger class, as POST /crux names it. Ranked in this order; see
 *  CONTEXT.md for what each means. */
export type DangerClass = "probable_release_area" | "fall_hazard" | "runout_area";

/** What one stretch of a Route turned out to be. `no_data` is never safe. */
export type SegmentClass = DangerClass | "none" | "no_data";

/** A run of samples of one class, drawn between the midpoints on either
 *  side. Distances are metres from the Route's start. */
export type CruxSegment = {
  class: SegmentClass;
  start_m: number;
  end_m: number;
  line: LineString;
};

/** Where a Danger zone begins, in the Route's direction of travel. */
export type Crux = {
  number: number;
  class: DangerClass;
  position: LatLng;
  distance_m: number;
  /** The whole Danger zone this Crux starts. */
  length_m: number;
  /** Highest release probability over the zone, for a Probable release area. */
  max_pra_percent?: number;
  /** Steepest ground over the zone, for a Fall hazard. */
  max_slope_deg?: number;
};

/** What POST /crux answers with. */
export type CruxResult = {
  segments: CruxSegment[];
  cruxes: Crux[];
  length_m: number;
  no_data_m: number;
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
