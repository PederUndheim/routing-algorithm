import type { Position } from "geojson";

const EARTH_RADIUS_M = 6_371_008.8;

/** The most points a line is opened with for editing: each is a handle to
 *  drag, and past this the map is more handles than line. */
export const MAX_EDIT_POINTS = 150;

/** How far a point lies from the segment a-b, in metres. Measured flat
 *  around a - fine at the scale of one segment of a route. */
const offsetFrom = (p: Position, a: Position, b: Position): number => {
  const rad = Math.PI / 180;
  const kx = Math.cos(a[1] * rad) * rad * EARTH_RADIUS_M;
  const ky = rad * EARTH_RADIUS_M;
  const bx = (b[0] - a[0]) * kx;
  const by = (b[1] - a[1]) * ky;
  const px = (p[0] - a[0]) * kx;
  const py = (p[1] - a[1]) * ky;
  const len2 = bx * bx + by * by;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, (px * bx + py * by) / len2));
  return Math.hypot(px - t * bx, py - t * by);
};

/** Douglas-Peucker: the fewest points that keep every dropped one within
 *  `tolerance_m` of the line. Both ends always stay. */
export const simplifyLine = (coords: readonly Position[], tolerance_m: number): Position[] => {
  if (coords.length <= 2) return [...coords];
  const keep = new Uint8Array(coords.length);
  keep[0] = 1;
  keep[coords.length - 1] = 1;
  const stack: [number, number][] = [[0, coords.length - 1]];
  while (stack.length > 0) {
    const [first, last] = stack.pop()!;
    let worst = -1;
    let worstOffset = tolerance_m;
    for (let i = first + 1; i < last; i++) {
      const offset = offsetFrom(coords[i], coords[first], coords[last]);
      if (offset > worstOffset) {
        worst = i;
        worstOffset = offset;
      }
    }
    if (worst >= 0) {
      keep[worst] = 1;
      stack.push([first, worst], [worst, last]);
    }
  }
  return coords.filter((_, i) => keep[i]);
};

/** An edited line with the detail the editor left out put back wherever it
 *  was not touched. `simplified` is what the editor was opened with, and
 *  `edited` what came back: between two of its points that are still there
 *  and still neighbours, the line runs as the original did - every point of
 *  it - rather than straight across. Anywhere else, as edited. */
export const restoreUnedited = (
  original: readonly Position[],
  simplified: readonly Position[],
  edited: readonly Position[]
): Position[] => {
  const key = (p: Position) => `${p[0]},${p[1]}`;
  // Where each simplified point sits in the original, and what follows it.
  const indexOf = new Map<string, number>();
  let from = 0;
  for (const p of simplified) {
    while (from < original.length && key(original[from]) !== key(p)) from++;
    if (from === original.length) return [...edited];
    indexOf.set(key(p), from);
  }
  const nextOf = new Map<string, string>();
  for (let i = 1; i < simplified.length; i++) nextOf.set(key(simplified[i - 1]), key(simplified[i]));

  const out: Position[] = [];
  for (let i = 0; i < edited.length; i++) {
    out.push(edited[i]);
    const next = edited[i + 1];
    if (!next || nextOf.get(key(edited[i])) !== key(next)) continue;
    const a = indexOf.get(key(edited[i]))!;
    const b = indexOf.get(key(next))!;
    // A line that comes back through a point it has already passed can
    // map one key to the wrong visit; then it is simply left straight.
    if (b > a) out.push(...original.slice(a + 1, b));
  }
  return out;
};

/** A routed or recorded line made few enough points to drag about: the
 *  tightest tolerance - from 2 m, doubling - that brings it down to
 *  `maxPoints`. A line already that short is left exactly as it is. */
export const simplifyForEditing = (
  coords: readonly Position[],
  maxPoints = MAX_EDIT_POINTS
): Position[] => {
  if (coords.length <= maxPoints) return [...coords];
  let tolerance = 2;
  let simplified = simplifyLine(coords, tolerance);
  while (simplified.length > maxPoints) {
    tolerance *= 2;
    simplified = simplifyLine(coords, tolerance);
  }
  return simplified;
};
