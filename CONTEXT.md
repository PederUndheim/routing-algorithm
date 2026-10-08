# Project Context

Keep this file short. It contains only durable knowledge shared across many tasks.

## Purpose

Ski-touring route planning over Norwegian terrain: a least-cost router over a
built cost surface, and a Crux Identifier that says where along a route the
terrain asks for attention.

## Vocabulary

- **Route** - one line in the app's list. Either *routed* (computed by the
  backend, has cost/detour and comes with a Corridor), *drawn* or *uploaded*
  (GPX/GeoJSON, has only a length until a Corridor is made for it). Editing
  any Route's line makes it like a drawn one: its router numbers and
  Corridor go. Routes are compared against each other, not tied to the
  start/end markers currently on the map.
- **Corridor** - the band of ground around a Route that costs little extra
  to cross instead. Two kinds, each with its own settings: a routed Route's
  is the near-optimal ground between its ends (`config.CORRIDOR`); any other
  Route's is the ground within reach of its own line, since such a line has
  no optimum to be near (`routing.line_corridor`, `config.LINE_CORRIDOR`).
- **Danger class** - what one stretch of ground is. Two of them, ranked;
  see Stable constraints.
- **Area** - consecutive runs merged into one piece of ground to decide
  about: short gaps closed, and two steep areas under `steep_gap_m` apart
  with only runout between joined into one. An area is one segment, one
  colour and at most one Crux.
- **Marks** - what a Steep slope area turns out to be: `probable_release_area`
  where PRA passes its threshold anywhere in it, `fall_hazard` where the
  slope reaches `fall_threshold` anywhere in it, both, or neither. Not
  classes of their own - they name the area, draw an icon on its Crux and
  turn it red.
- **Crux** - the *first* sample of an area that outranks the area before it,
  in the line's own direction of travel: where a ski tourer following the
  route arrives at something worse than what they were on.
- **Segment** - one area, drawn midpoint-to-midpoint so adjacent segments
  meet. A segment carries the same class and marks as its Crux, so the line
  and the marker always say the same thing.

## Stable constraints

- **Danger class ranking**, highest first. A sample takes the highest-ranked
  class that applies:

  | Class | Rank | Test | Screen name |
  |---|---|---|---|
  | `steep_slope` | 2 | slope >= 30 deg, no upper cap | Steep slope |
  | `runout_area` | 1 | 0 <= runout < 10000 m | Runout area |

  Below both: `none` and `no_data`, which both rank 0 though `no_data` is
  never safe. A Runout area shorter than 20 m reads as `none`.

  The classes are what the slope map underneath shades, so a Steep slope is
  the thing under the cursor. PRA is deliberately *not* a class: a release
  area off steep ground would put a marker on terrain that looks flat.
- **Raster sentinels are answers, not holes.** PRA -128 means no release area;
  runout 10000 means beyond reach. Only the slope raster's nodata is missing
  data. Reading the first two as unknown would grey out most of every route.
- Thresholds live in `config.CRUX`, nowhere else.
- **A Crux where an area outranks the one before it, and nowhere else.**
  Arriving at steep ground always places one, and so does the first runout
  off safe ground. Runout below a slope just crossed does not: that slope
  already has its marker, and the line turning orange says the rest. It is
  the one colour that carries no marker of its own, and it is deliberate.
- **Merging only ever merges.** No pass invents a class that was not in the
  runs it joined: a closed gap reads as the *lower* of its neighbours, and
  only runout is ever swallowed between two steep areas.
- **One area, one colour, and the marker matches it.** A merged area takes
  the worst of what it holds, line and marker alike, so the line never
  changes colour without a reason the markers can account for.

## Architecture map

- `skimap/skimap/` - the library. `crux.py` (Crux Identifier), `config.py`
  (all thresholds), `exposure.py` (raster sampling), `paths.py`.
- `skimap/app/backend/` - FastAPI over the library: `server.py` routes,
  `service.py`, `corridor.py`.
- `skimap/app/frontend/src/` - React + MUI + react-leaflet.
  - `App.tsx` owns all cross-cutting state; `routes/routeList.ts` is the
    Route store, read through `useSyncExternalStore`.
  - `map/` draws: `RouteLines` (segments), `CruxMarkers`, `CorridorOverlay`.
    `clusterCruxes` groups markers that would overlap at the current zoom;
    it takes projection and size as arguments, so it is Leaflet-free and
    unit-tested.
  - `routing/` is the left drawer: `RoutePanel` -> `RouteListSection`,
    `SelectedRoute`.
  - `theme.ts` holds every colour; `dangerClasses.ts` maps class -> name and
    MUI icon.

## Conventions

- Three brand colours only (`COLORS`: teal, orange, panel grey). Danger
  classes have their own scale in `CRUX_COLORS`.
- Comments explain *why*, in prose, not what the line does.
- `routing_app/` is the previous generation of the app, kept as reference
  for UI patterns. Not live.

## Decision index

- 2026-09-14 - [Split fall hazard at 50 degrees](docs/decisions/2026-09-14-split-fall-hazard-at-50-degrees.md)
