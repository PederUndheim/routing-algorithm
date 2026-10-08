import type { LineString, Position } from "geojson";

import { problemHazards, problemOf } from "../crux/assessment";
import { dangerName } from "../dangerClasses";
import { dangerColor } from "../theme";
import type {
  Answers,
  CruxEntry,
  CruxProblem,
  CruxResult,
  Extent,
  Factor,
  LatLng,
  ManualCruxInput,
  Rating,
  RouteResponse,
} from "../types";
import { RouteFileError, parseRouteFile } from "./parseRouteFile";

const EARTH_RADIUS_M = 6_371_008.8;

/** Length of a WGS84 line in metres, great circle between each pair. The
 *  backend measures a routed Route on the 25833 grid instead; the two agree
 *  to well under a percent at these latitudes. */
export const geodesicLength = (coordinates: Position[]): number => {
  const rad = Math.PI / 180;
  let total = 0;
  for (let i = 1; i < coordinates.length; i++) {
    const [lng1, lat1] = coordinates[i - 1];
    const [lng2, lat2] = coordinates[i];
    const dLat = (lat2 - lat1) * rad;
    const dLng = (lng2 - lng1) * rad;
    const h =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLng / 2) ** 2;
    total += 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
  }
  return total;
};

/** `name` if nothing in the list has it yet, else "name (2)", "name (3)" -
 *  the lowest that is free, so the list never shows two the same. */
const uniqueName = (name: string, taken: ReadonlySet<string>): string => {
  if (!taken.has(name)) return name;
  for (let n = 2; ; n++) {
    const candidate = `${name} (${n})`;
    if (!taken.has(candidate)) return candidate;
  }
};

/** Where a Route came from: computed by the router, drawn on the map, or
 *  uploaded as a file. */
export type RouteSource = "routed" | "drawn" | "uploaded";

/** What only a routed Route has: the router's own numbers and its corridor. */
export type RoutedExtras = Pick<
  RouteResponse,
  "corridor" | "straight_m" | "detour" | "cost" | "seconds"
>;

/** One entry in the route list. See CONTEXT.md: whatever its origin, a Route. */
export type Route = {
  id: string;
  name: string;
  source: RouteSource;
  /** WGS84, GeoJSON order - [lng, lat]. */
  line: LineString;
  lengthM: number;
  visible: boolean;
  routed: RoutedExtras | null;
  /** The Crux Identifier's answer, once it has been run on this Route. */
  crux: CruxResult | null;
  /** Every Crux on the Route - identified and placed by hand - in route
   *  order, with what has been answered about each. */
  cruxes: readonly CruxEntry[];
};

/** What the Edit crux form gives back. */
export type CruxDetailsInput = { description: string; problem: CruxProblem; color: string };

/** Where a Crux's marker is, all of it: enough to put it back. */
export type CruxMarker = Pick<CruxEntry, "position" | "distance_m" | "moved">;

/** Whether the user has made anything of an identified Crux - rated it,
 *  decided about it, moved, edited or deleted it - which identifying the
 *  Route again would throw away. */
export const isEdited = (crux: CruxEntry): boolean =>
  crux.source === "identified" &&
  (Object.keys(crux.answers).length > 0 ||
    crux.overall !== undefined ||
    crux.keep !== undefined ||
    crux.deleted === true ||
    crux.moved === true ||
    crux.extent !== undefined);

/** In route order, numbered 1, 2, 3 along it. */
const ordered = (cruxes: readonly CruxEntry[]): CruxEntry[] =>
  [...cruxes]
    .sort((a, b) => a.distance_m - b.distance_m)
    .map((crux, i) => ({ ...crux, number: i + 1 }));

export type RouteListState = {
  routes: readonly Route[];
  /** The Selected route. Never more than one; null only when nothing is. */
  selectedId: string | null;
};

/** A file that could not be used, and why - worded to follow the file name. */
export type UploadError = { fileName: string; reason: string };

export type UploadResult = {
  added: readonly Route[];
  errors: readonly UploadError[];
};

export type RouteList = {
  getState: () => RouteListState;
  subscribe: (listener: () => void) => () => void;
  /** Append a freshly routed Route and make it the Selected route. */
  addRouted: (response: RouteResponse) => Route;
  /** Append a Route drawn on the map and make it the Selected route. */
  addDrawn: (coordinates: Position[]) => Route;
  /** Replace a Route's line, as when a drawn one is edited. Its crux
   *  result described the old line, so it goes; the Route is shown. */
  updateLine: (id: string, coordinates: Position[]) => void;
  /** Read GPX/GeoJSON files into uploaded Routes, one per track or line.
   *  A bad file is reported and skipped; the rest still load, and the last
   *  Route added becomes the Selected route. */
  upload: (files: Iterable<File>) => Promise<UploadResult>;
  select: (id: string) => void;
  /** Hide or show a Route. Purely visual: the selection never changes. */
  toggleVisible: (id: string) => void;
  /** Drop a Route. If it was the Selected route, the one above it takes
   *  over - or the one below, when it was at the top. */
  remove: (id: string) => void;
  /** Give a Route its crux result, replacing any earlier one, and show it
   *  if it was hidden - the result was asked for. A Route deleted while it
   *  was being analysed is simply not there to receive it. */
  attachCrux: (id: string, result: CruxResult) => void;
  /** Place a Crux by hand on a Route, in its place along it. */
  addManualCrux: (routeId: string, input: ManualCruxInput) => CruxEntry | null;
  /** Delete a Crux: it leaves the map and waits on the list's deleted shelf,
   *  where it can be brought back. */
  deleteCrux: (routeId: string, cruxId: string) => void;
  /** Bring a deleted Crux back as it was. */
  undeleteCrux: (routeId: string, cruxId: string) => void;
  /** Move a Crux's marker to another spot on the Route, keeping everything
   *  the user has made of it. Its place among the others, and so its number,
   *  follows, and its marker now stands exactly on the spot. What it colours
   *  stays where it was: that is its extent, edited on its own. */
  moveCrux: (
    routeId: string,
    cruxId: string,
    spot: { position: LatLng; distance_m: number }
  ) => void;
  /** Put a Crux's marker back exactly as it was - moved or not - as when
   *  an edit that moved it along is given up. */
  setMarker: (routeId: string, cruxId: string, marker: CruxMarker) => void;
  /** Change what a Crux is called, its symbol and its colour. A name or
   *  colour that is only what its symbol gives it anyway is not stored, so
   *  it keeps following the symbol. Changing the symbol keeps what the
   *  analysis measured - steepness, release probability - and drops only
   *  the marks the old symbol carried. */
  editCrux: (routeId: string, cruxId: string, details: CruxDetailsInput) => void;
  /** Set the stretch a Crux colours. Undefined goes back to what it had -
   *  an identified Crux's area as the analysis found it, or nothing for one
   *  placed by hand. */
  setExtent: (routeId: string, cruxId: string, extent: Extent | undefined) => void;
  /** Rate one aspect of a Crux; undefined takes the rating back. */
  setAnswer: (routeId: string, cruxId: string, factor: Factor, value: Rating | undefined) => void;
  /** The user's overall rating of a Crux; undefined takes it back. */
  setOverall: (routeId: string, cruxId: string, value: Rating | undefined) => void;
  /** Whether the user wants a Crux in the list; undefined is undecided. */
  setKeep: (routeId: string, cruxId: string, keep: boolean | undefined) => void;
  /** Put a Crux the user chose not to keep back in the list, as undecided,
   *  keeping its ratings. */
  restoreCrux: (routeId: string, cruxId: string) => void;
};

/** The app's list of Routes and every action on it.
 *
 * A store rather than React state, so the invariants live in one place and
 * can be tested without rendering anything: at most one Selected route, and
 * the newest Route is it. The app reads it through useSyncExternalStore.
 * Session-only - nothing here is persisted.
 */
export const createRouteList = (): RouteList => {
  let state: RouteListState = { routes: [], selectedId: null };
  const listeners = new Set<() => void>();
  let nextId = 1;
  let routedCount = 0;
  let drawnCount = 0;
  let nextCruxId = 1;

  const set = (next: RouteListState) => {
    state = next;
    listeners.forEach((listener) => listener());
  };

  const updateCruxes = (
    routeId: string,
    change: (cruxes: readonly CruxEntry[]) => CruxEntry[]
  ) => {
    if (!state.routes.some((r) => r.id === routeId)) return;
    set({
      ...state,
      routes: state.routes.map((r) =>
        r.id === routeId ? { ...r, cruxes: ordered(change(r.cruxes)) } : r
      ),
    });
  };

  const updateCrux = (
    routeId: string,
    cruxId: string,
    change: (crux: CruxEntry) => CruxEntry
  ) => updateCruxes(routeId, (cruxes) => cruxes.map((c) => (c.id === cruxId ? change(c) : c)));

  return {
    getState: () => state,

    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },

    addRouted: (response) => {
      routedCount += 1;
      const route: Route = {
        id: `route-${nextId++}`,
        name: uniqueName(`Route ${routedCount}`, new Set(state.routes.map((r) => r.name))),
        source: "routed",
        line: response.route.features[0].geometry as LineString,
        lengthM: response.length_m,
        visible: true,
        routed: {
          corridor: response.corridor,
          straight_m: response.straight_m,
          detour: response.detour,
          cost: response.cost,
          seconds: response.seconds,
        },
        crux: null,
        cruxes: [],
      };
      set({ routes: [...state.routes, route], selectedId: route.id });
      return route;
    },

    addDrawn: (coordinates) => {
      drawnCount += 1;
      const route: Route = {
        id: `route-${nextId++}`,
        name: uniqueName(`Drawn route ${drawnCount}`, new Set(state.routes.map((r) => r.name))),
        source: "drawn",
        line: { type: "LineString", coordinates },
        lengthM: geodesicLength(coordinates),
        visible: true,
        routed: null,
        crux: null,
        cruxes: [],
      };
      set({ routes: [...state.routes, route], selectedId: route.id });
      return route;
    },

    updateLine: (id, coordinates) => {
      set({
        ...state,
        routes: state.routes.map((r) =>
          r.id === id
            ? {
                ...r,
                line: { type: "LineString", coordinates },
                lengthM: geodesicLength(coordinates),
                visible: true,
                crux: null,
                // Placed on the old line, so they no longer sit on this one.
                cruxes: [],
              }
            : r
        ),
      });
    },

    upload: async (files) => {
      const lines: { fileName: string; coordinates: Position[] }[] = [];
      const errors: UploadError[] = [];

      for (const file of files) {
        try {
          for (const coordinates of parseRouteFile(file.name, await file.text())) {
            lines.push({ fileName: file.name, coordinates });
          }
        } catch (err) {
          errors.push({
            fileName: file.name,
            reason: err instanceof RouteFileError ? err.message : "could not be read",
          });
        }
      }

      // Everything below reads the list after the last await, so a Route
      // routed while the files were being read is neither overwritten by a
      // stale copy of the list nor given a name one of these then takes.
      const taken = new Set(state.routes.map((r) => r.name));
      const added = lines.map(({ fileName, coordinates }): Route => {
        const name = uniqueName(fileName, taken);
        taken.add(name);
        return {
          id: `route-${nextId++}`,
          name,
          source: "uploaded",
          line: { type: "LineString", coordinates },
          lengthM: geodesicLength(coordinates),
          visible: true,
          routed: null,
          crux: null,
          cruxes: [],
        };
      });

      if (added.length > 0) {
        set({ routes: [...state.routes, ...added], selectedId: added[added.length - 1].id });
      }
      return { added, errors };
    },

    select: (id) => {
      if (state.routes.some((r) => r.id === id)) set({ ...state, selectedId: id });
    },

    toggleVisible: (id) => {
      set({
        ...state,
        routes: state.routes.map((r) => (r.id === id ? { ...r, visible: !r.visible } : r)),
      });
    },

    remove: (id) => {
      const index = state.routes.findIndex((r) => r.id === id);
      if (index < 0) return;
      const routes = state.routes.filter((r) => r.id !== id);
      const selectedId =
        state.selectedId === id
          ? (routes[Math.max(index - 1, 0)]?.id ?? null)
          : state.selectedId;
      set({ routes, selectedId });
    },

    attachCrux: (id, result) => {
      if (!state.routes.some((r) => r.id === id)) return;
      // The new result replaces the identified Cruxes and everything the user
      // made of them - they may not be the same ones. Hand-placed ones stay.
      // Their areas are rescaled from the backend's measure of the line to
      // this one, so a handle dragged along it lands where the colour does.
      set({
        ...state,
        routes: state.routes.map((r) => {
          if (r.id !== id) return r;
          const scale = result.length_m > 0 ? geodesicLength(r.line.coordinates) / result.length_m : 1;
          const identified = result.cruxes.map(
            (crux): CruxEntry => ({
              ...crux,
              id: `crux-${nextCruxId++}`,
              source: "identified",
              answers: {},
              area: {
                start_m: crux.distance_m * scale,
                end_m: (crux.distance_m + crux.length_m) * scale,
              },
            })
          );
          const manual = r.cruxes.filter((c) => c.source === "manual");
          return { ...r, crux: result, cruxes: ordered([...identified, ...manual]), visible: true };
        }),
      });
    },

    addManualCrux: (routeId, input) => {
      if (!state.routes.some((r) => r.id === routeId)) return null;
      const id = `crux-${nextCruxId++}`;
      const description = input.description.trim();
      updateCruxes(routeId, (cruxes) => [
        ...cruxes,
        {
          ...problemHazards(input.problem),
          number: 0,
          position: input.position,
          distance_m: input.distance_m,
          length_m: 0,
          id,
          source: "manual",
          answers: {},
          ...(input.length_m > 0
            ? { extent: { start_m: input.distance_m, end_m: input.distance_m + input.length_m } }
            : {}),
          color: input.color,
          ...(description ? { description } : {}),
        },
      ]);
      set({
        ...state,
        routes: state.routes.map((r) => (r.id === routeId ? { ...r, visible: true } : r)),
      });
      const route = state.routes.find((r) => r.id === routeId)!;
      return route.cruxes.find((c) => c.id === id) ?? null;
    },

    deleteCrux: (routeId, cruxId) => {
      updateCrux(routeId, cruxId, (crux) => ({ ...crux, deleted: true }));
    },

    undeleteCrux: (routeId, cruxId) => {
      updateCrux(routeId, cruxId, ({ deleted: _deleted, ...crux }) => crux);
    },

    moveCrux: (routeId, cruxId, { position, distance_m }) => {
      updateCrux(routeId, cruxId, (crux) => ({ ...crux, position, distance_m, moved: true }));
    },

    setMarker: (routeId, cruxId, { position, distance_m, moved }) => {
      updateCrux(routeId, cruxId, ({ moved: _old, ...crux }) => ({
        ...crux,
        position,
        distance_m,
        ...(moved ? { moved } : {}),
      }));
    },

    setAnswer: (routeId, cruxId, factor, value) => {
      updateCrux(routeId, cruxId, (crux) => {
        const answers: Answers = { ...crux.answers };
        if (value === undefined) delete answers[factor];
        else answers[factor] = value;
        return { ...crux, answers };
      });
    },

    editCrux: (routeId, cruxId, { description, problem, color }) => {
      updateCrux(routeId, cruxId, (crux) => {
        const {
          description: _description,
          color: _color,
          probable_release_area: _release,
          fall_hazard: _fall,
          ...rest
        } = crux;
        // Unchanged, the symbol keeps the marks it had - an area that is
        // both a release area and a fall hazard stays both.
        const hazards =
          problem === problemOf(crux)
            ? {
                class: crux.class,
                ...(crux.probable_release_area ? { probable_release_area: true } : {}),
                ...(crux.fall_hazard ? { fall_hazard: true } : {}),
              }
            : problemHazards(problem);
        const name = description.trim();
        const next: CruxEntry = { ...rest, ...hazards };
        if (name && name !== dangerName(next)) next.description = name;
        if (color !== dangerColor(next)) next.color = color;
        return next;
      });
    },

    setExtent: (routeId, cruxId, extent) => {
      updateCrux(routeId, cruxId, ({ extent: _old, ...crux }) =>
        extent ? { ...crux, extent } : crux
      );
    },

    setOverall: (routeId, cruxId, value) => {
      updateCrux(routeId, cruxId, ({ overall: _old, ...crux }) =>
        value ? { ...crux, overall: value } : crux
      );
    },

    setKeep: (routeId, cruxId, keep) => {
      updateCrux(routeId, cruxId, ({ keep: _old, ...crux }) =>
        keep === undefined ? crux : { ...crux, keep }
      );
    },

    restoreCrux: (routeId, cruxId) => {
      updateCrux(routeId, cruxId, ({ keep: _old, ...crux }) => crux);
    },
  };
};
