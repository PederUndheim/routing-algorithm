import type { FeatureCollection, LineString } from "geojson";

export type LatLng = { lat: number; lng: number };

/** Which point the next map click sets, or null for an ordinary click. */
export type PickMode = "start" | "end" | null;

/** The three ways to add a Route: the router between two points, a line
 *  drawn on the map, or a GPX/GeoJSON file. Exactly one is chosen. */
export type AddMode = "generate" | "draw" | "upload";

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
export type DangerClass = "steep_slope" | "runout_area";

/** What one stretch of a Route turned out to be. `no_data` is never safe. */
export type SegmentClass = DangerClass | "none" | "no_data";

/** What a Steep slope area turns out to be, over the whole area. Not classes
 *  of their own: they mark the area's Crux and turn it red. A Runout area
 *  carries none of them, and an area can be both at once. */
export type Hazards = {
  probable_release_area?: boolean;
  fall_hazard?: boolean;
  /** Steepest ground in the area, for a Steep slope. */
  max_slope_deg?: number;
  /** Highest release probability in the area, when it is a release area. */
  max_pra_percent?: number;
};

/** A run of samples of one class, drawn between the midpoints on either
 *  side. Distances are metres from the Route's start. */
export type CruxSegment = Hazards & {
  class: SegmentClass;
  start_m: number;
  end_m: number;
  line: LineString;
};

/** Where an area begins that outranks the one before it, in the Route's
 *  direction of travel - so arriving at steep ground always places one, and
 *  so does the first runout off safe ground. Runout below a slope you have
 *  just crossed does not: the line turns orange with no marker of its own.
 *
 *  Its fields are the ones its segment carries, so a marker and the stretch
 *  it stands on always say and show the same thing. */
export type Crux = Hazards & {
  number: number;
  class: DangerClass;
  position: LatLng;
  /** Where the area starts, from the start of the Route. */
  distance_m: number;
  /** The whole area, runout merged into it included. */
  length_m: number;
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

/** The slope categories a Crux is assessed in. The questions asked, and how
 *  many yes answers make it critical, depend on which one it is in. */
export type SlopeCategory = "lt30" | "30_34" | "35_39" | "gt39";

/** What the user is asked about a Crux, one yes/no each. A yes always
 *  means the Crux is more serious. */
export type Factor =
  | "slope_size"
  | "release_volume"
  | "terrain_traps"
  | "safe_spots"
  | "remote_triggering";

export type Answers = Partial<Record<Factor, boolean>>;

/** What a hand-placed Crux is: the same problems the identifier names, so it
 *  is drawn with the same symbol. */
export type CruxProblem = "steep_slope" | "release_area" | "fall_hazard" | "runout_area";

/** A Crux in a Route's list: one the identifier found, or one placed by
 *  hand, with what the user has answered about it. `number` is its place
 *  along the Route among all of them, renumbered whenever one is added. */
export type CruxEntry = Crux & {
  id: string;
  source: "identified" | "manual";
  category: SlopeCategory;
  answers: Answers;
  /** A hand-placed Crux's own colour and words; the identifier's have none. */
  color?: string;
  description?: string;
};

/** What the Add crux form gives back. */
export type ManualCruxInput = {
  position: LatLng;
  distance_m: number;
  category: SlopeCategory;
  problem: CruxProblem;
  color: string;
  description: string;
};
