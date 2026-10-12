import type { FeatureCollection, LineString } from "geojson";

export type LatLng = { lat: number; lng: number };

/** The points Generate routes through, start first and end last, and how
 *  each leg between two neighbours goes - one network fewer than points,
 *  and none until there are two. */
export type Waypoints = {
  points: readonly LatLng[];
  networks: readonly RouteNetwork[];
};

/** What the next map click does to the Waypoints, or null for an ordinary
 *  click. "sequence" is Pick points: the start, then the end, then done.
 *  "replace" puts one point somewhere else, and "insert" adds one at
 *  `index`, the rest moved along - at the end, it is the new end. */
export type PickMode =
  | { kind: "sequence" }
  | { kind: "replace"; index: number }
  | { kind: "insert"; index: number }
  | null;

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
  /** A place the user has marked to check the snow conditions - dig, test,
   *  look. Never from the backend: only a Crux the user gives this symbol. */
  snow_check?: boolean;
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

/** What the router walks on one leg: over the terrain on the cost surface,
 *  the ski touring default, or along the road network by car. */
export type RouteNetwork = "terrain" | "road";

/** What a whole routed Route walked: one network on every leg, or a mix. */
export type RoutedNetwork = RouteNetwork | "mixed";

/** A stretch of a line as [start_m, end_m] from its start, measured on the
 *  backend's metric grid. */
export type Stretch = [number, number];

/** One leg of a routed Route: how it went, and where along the joined line
 *  it starts and ends. */
export type RouteLeg = {
  network: RouteNetwork;
  start_m: number;
  end_m: number;
  cost: number;
};

/** What POST /route answers with. Lengths are metres. Cost is unitless over
 *  terrain - the cumulative cost surface value, comparable only against
 *  itself - and the estimated drive in seconds on roads; null for a mix of
 *  the two, which add up to nothing. */
export type RouteResponse = {
  route: FeatureCollection;
  /** The terrain legs' corridors as one picture. None with no terrain
   *  leg: the car stays on the road, so there is no band of nearly-as-good
   *  ground beside it. */
  corridor: Corridor | null;
  /** Absent from an older backend, which only routes over terrain. */
  network?: RoutedNetwork;
  length_m: number;
  /** Summed over the legs: the straight lines between neighbouring points. */
  straight_m: number;
  detour: number;
  cost: number | null;
  seconds: number;
  /** Absent from a backend older than waypoints. */
  legs?: RouteLeg[];
  /** The road legs' tunnels and ferry crossings, along the whole line: off
   *  the terrain the Crux Identifier reads, so they are handed back to it
   *  to leave out. */
  tunnels?: Stretch[];
  ferries?: Stretch[];
};

/** What POST /corridor answers with: the corridor around a line the router
 *  did not make - drawn, uploaded, or a routed one since edited. Not the
 *  routed kind: it is the ground within reach of the line itself, on the
 *  same budget, since such a line has no optimum to be near. */
export type CorridorResponse = {
  corridor: Corridor;
  /** The line's own cost, on the same scale as RouteResponse's. */
  cost: number;
  seconds: number;
};

/** What ground a stretch of line crosses, in metres, read sample by sample.
 *  `release_m` and `fall_m` are the steep ground that is also a release
 *  area or a fall hazard - part of `steep_m`, not beside it. */
export type GroundSummary = {
  length_m: number;
  steep_m: number;
  release_m: number;
  fall_m: number;
  runout_m: number;
  no_data_m: number;
};

/** A stretch of a drawn or uploaded line where a clearly cheaper way runs
 *  close beside it, as POST /improve finds one. `start_m` and `end_m` are on
 *  the backend's grid, where it leaves and rejoins the line; `line` runs
 *  from the one point to the other. */
export type Suggestion = {
  start_m: number;
  end_m: number;
  line: LineString;
  cost: number;
  old_cost: number;
  /** The stretch it replaces, and the new way. */
  before: GroundSummary;
  after: GroundSummary;
};

/** What POST /improve answers with. `length_m` is the whole line on the
 *  backend's grid, for scaling `start_m` and `end_m` to the app's measure. */
export type ImproveResponse = {
  suggestions: Suggestion[];
  length_m: number;
  seconds: number;
};

/** The aspects of a Crux the user weighs up. */
export type Factor =
  | "slope_size"
  | "release_volume"
  | "terrain_traps"
  | "safe_spots"
  | "remote_triggering"
  | "natural_release";

/** The user's judgement of one aspect, or of the Crux overall, on a
 *  five-step scale from clearly in their favour to clearly against them. */
export type Rating = "very_good" | "good" | "neutral" | "bad" | "very_bad";

export type Answers = Partial<Record<Factor, Rating>>;

/** A stretch of a Route, in metres along its line as the frontend measures
 *  it - the same measure `sliceLine` and `nearestOnLine` use. */
export type Extent = { start_m: number; end_m: number };

/** What a hand-placed Crux is: the same problems the identifier names, so it
 *  is drawn with the same symbol. */
export type CruxProblem =
  | "steep_slope"
  | "release_area"
  | "fall_hazard"
  | "runout_area"
  | "snow_check";

/** A Crux in a Route's list: one the identifier found, or one placed by
 *  hand, with what the user has made of it. `number` is its place along the
 *  Route among all of them, renumbered whenever one is added or moved. */
export type CruxEntry = Crux & {
  id: string;
  source: "identified" | "manual";
  answers: Answers;
  /** The user's own overall rating, read off their answers. Shown with the
   *  Crux; it decides nothing by itself. */
  overall?: Rating;
  /** Whether the user wants it in the list: false puts it on the not-kept
   *  shelf and off the map. Undecided counts as kept. */
  keep?: boolean;
  /** Deleted by the user: kept out of sight, on the list's deleted shelf,
   *  until it is brought back. */
  deleted?: boolean;
  /** Moved by the user, so its marker stands exactly on its spot instead of
   *  ahead of it like an identified Crux's. */
  moved?: boolean;
  /** An identified Crux's area as the analysis found it - what its segments
   *  colour. */
  area?: Extent;
  /** The stretch the user has given it to colour: a hand-placed Crux's
   *  stretch, or an identified one's area as the user has edited it. */
  extent?: Extent;
  /** A hand-placed Crux's own colour and words; the identifier's have none. */
  color?: string;
  description?: string;
} & CruxNotes;

/** What the user writes down about a Crux beside their ratings: why they
 *  assessed it as they did, and how the group will handle it - one at a
 *  time down the slope, regroup at a safe spot. Each absent until written. */
export type CruxNotes = {
  comment?: string;
  group_measures?: string;
};

export type CruxNote = keyof CruxNotes;

/** What the Add crux form gives back. */
export type ManualCruxInput = {
  position: LatLng;
  distance_m: number;
  problem: CruxProblem;
  color: string;
  description: string;
  /** How much of the line ahead of the spot is coloured, in metres. 0 is a
   *  marker alone. */
  length_m: number;
};
