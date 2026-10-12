import type { LineString, Position } from "geojson";

import type { GroundSummary, ImproveResponse, Suggestion } from "../types";
import { geodesicLength } from "./routeList";
import { sliceLine } from "./snap";

/** A Suggestion as a Route keeps it: an id, and where it leaves and rejoins
 *  the line in the app's own measure - the one sliceLine cuts by. */
export type RouteSuggestion = Suggestion & { id: string; startM: number; endM: number };

const EARTH_RADIUS_M = 6_371_008.8;

/** How far along `line` the point nearest to `point` is, looking only
 *  within `window_m` of `near_m`.
 *
 *  Windowed because a tour passes the same ground twice - up and down a
 *  summit, out and back along a valley - and the nearest point overall can
 *  be on the wrong pass. `near_m` is where it should be, near enough. */
export const locateNear = (
  line: LineString,
  point: Position,
  near_m: number,
  window_m = 250
): number => {
  const coords = line.coordinates;
  const rad = Math.PI / 180;
  let best = { d2: Infinity, along: near_m };
  let along = 0;
  for (let i = 1; i < coords.length; i++) {
    const segment = geodesicLength([coords[i - 1], coords[i]]);
    const start = along;
    along += segment;
    if (along < near_m - window_m || start > near_m + window_m) continue;

    const [lng1, lat1] = coords[i - 1];
    const [lng2, lat2] = coords[i];
    const kx = Math.cos(((lat1 + lat2) / 2) * rad) * rad * EARTH_RADIUS_M;
    const ky = rad * EARTH_RADIUS_M;
    const bx = (lng2 - lng1) * kx;
    const by = (lat2 - lat1) * ky;
    const px = (point[0] - lng1) * kx;
    const py = (point[1] - lat1) * ky;
    const len2 = bx * bx + by * by;
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, (px * bx + py * by) / len2));
    const d2 = (px - t * bx) ** 2 + (py - t * by) ** 2;
    if (d2 < best.d2) best = { d2, along: start + t * segment };
  }
  return best.along;
};

const ends = (s: Suggestion): [Position, Position] => {
  const c = s.line.coordinates;
  return [c[0], c[c.length - 1]];
};

/** A response's suggestions, placed on the line they were found for. The
 *  backend measures on its own grid, so its distances are scaled to this
 *  line's length first, as a Crux's are, and then each end is found
 *  exactly near there. */
export const placeSuggestions = (
  line: LineString,
  response: ImproveResponse,
  nextId: () => string
): RouteSuggestion[] => {
  const scale = response.length_m > 0 ? geodesicLength(line.coordinates) / response.length_m : 1;
  return response.suggestions
    .map((s): RouteSuggestion => {
      const [first, last] = ends(s);
      return {
        ...s,
        id: nextId(),
        startM: locateNear(line, first, s.start_m * scale),
        endM: locateNear(line, last, s.end_m * scale),
      };
    })
    .filter((s) => s.endM > s.startM);
};

/** The line with one suggestion taken: the same points up to where it
 *  leaves, its way, and the same points again from where it rejoins - so
 *  the ground on either side is untouched, and keeps its analysis. */
export const spliceSuggestion = (line: LineString, s: RouteSuggestion): Position[] => {
  const before = sliceLine(line, 0, s.startM);
  const after = sliceLine(line, s.endM, geodesicLength(line.coordinates));
  // The way's own ends are the same two points of the line; each is kept
  // only where the line has no point of its own there.
  const way = s.line.coordinates.slice(
    before.length > 0 ? 1 : 0,
    after.length > 0 ? -1 : undefined
  );
  // An end found a hair past one of the line's own points slices to that
  // point and another a millimetre on: one place, not a step.
  return [...before, ...way, ...after].filter(
    (p, i, all) =>
      i === 0 || Math.abs(p[0] - all[i - 1][0]) > 1e-8 || Math.abs(p[1] - all[i - 1][1]) > 1e-8
  );
};

/** The other suggestions, found again on the line after one was taken.
 *  Everything after it moved along by however much longer or shorter it
 *  made the line; nothing before it moved. */
export const relocate = (
  others: readonly RouteSuggestion[],
  taken: RouteSuggestion,
  oldLine: LineString,
  newLine: LineString
): RouteSuggestion[] => {
  const shift = geodesicLength(newLine.coordinates) - geodesicLength(oldLine.coordinates);
  return others.map((s) => {
    const by = s.startM >= taken.endM - 0.5 ? shift : 0;
    const [first, last] = ends(s);
    return {
      ...s,
      startM: locateNear(newLine, first, s.startM + by),
      endM: locateNear(newLine, last, s.endM + by),
    };
  });
};

/** What a suggestion does to the danger along the stretch: takes the line
 *  off steep ground, puts it on more, or neither - the cost surface finds
 *  the going easier there, which may be worth having but is not safer.
 *
 *  Steep ground counts once, and again where it is also a release area or a
 *  fall hazard, so swapping a release slope for a plain steep one is safer.
 *  Runout is left out: a way off a slope often runs below it, and the
 *  Danger classes rank steep ground first. A sample stands for 10 m, so a
 *  difference under that is the sampling, not the way. */
export type Verdict = "safer" | "riskier" | "easier";

const danger = (g: GroundSummary): number => g.steep_m + g.release_m + g.fall_m;

export const verdictOf = (s: Suggestion): Verdict => {
  const change = danger(s.after) - danger(s.before);
  if (change <= -10) return "safer";
  if (change >= 10) return "riskier";
  return "easier";
};
