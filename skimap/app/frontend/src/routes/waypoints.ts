import type { LatLng, PickMode, RouteNetwork, Waypoints } from "../types";

/** No points yet. */
export const NO_WAYPOINTS: Waypoints = { points: [], networks: [] };

/** How a leg goes until the user says otherwise: over the terrain. Driving
 *  is something to choose, never something to be surprised by. */
export const DEFAULT_NETWORK: RouteNetwork = "terrain";

/** What the panel and the map call a point: by its place on the route. */
export const pointLabel = (index: number, count: number): string => {
  if (index === 0) return "Start";
  if (index === count - 1) return "End";
  return `Waypoint ${index}`;
};

/** A new point at `index`, the rest moved along. Into the middle of a leg,
 *  both halves go as the leg did; before the start or after the end, the
 *  new leg goes over the terrain. */
export const insertPoint = (w: Waypoints, index: number, point: LatLng): Waypoints => {
  const points = [...w.points.slice(0, index), point, ...w.points.slice(index)];
  if (points.length < 2) return { points, networks: [] };

  const networks = [...w.networks];
  if (index === 0) networks.unshift(DEFAULT_NETWORK);
  else if (index >= w.points.length) networks.push(DEFAULT_NETWORK);
  else networks.splice(index, 0, w.networks[index - 1]);
  return { points, networks };
};

/** Point `index` gone. The start or the end takes its one leg with it; a
 *  waypoint's two legs become one, going as the first of them did. */
export const removePoint = (w: Waypoints, index: number): Waypoints => {
  const points = w.points.filter((_, i) => i !== index);
  if (points.length < 2) return { points, networks: [] };

  const networks = [...w.networks];
  networks.splice(index === w.points.length - 1 ? index - 1 : index, 1);
  return { points, networks };
};

export const movePoint = (w: Waypoints, index: number, point: LatLng): Waypoints => ({
  ...w,
  points: w.points.map((p, i) => (i === index ? point : p)),
});

export const setNetwork = (w: Waypoints, leg: number, network: RouteNetwork): Waypoints => ({
  ...w,
  networks: w.networks.map((n, i) => (i === leg ? network : n)),
});

/** A map click while picking: the points it makes, and whether the next
 *  click picks too. Pick points takes the start and then the end, one
 *  after the other; the rest are one click each. */
export const pick = (
  w: Waypoints,
  mode: NonNullable<PickMode>,
  point: LatLng
): { waypoints: Waypoints; mode: PickMode } => {
  switch (mode.kind) {
    case "sequence": {
      const waypoints = insertPoint(w, w.points.length, point);
      return { waypoints, mode: waypoints.points.length >= 2 ? null : mode };
    }
    case "replace":
      return { waypoints: movePoint(w, mode.index, point), mode: null };
    case "insert":
      return { waypoints: insertPoint(w, mode.index, point), mode: null };
  }
};

/** Whether every leg is driven - the route is then a drive, with no
 *  corridor. */
export const allRoad = (w: Waypoints): boolean =>
  w.networks.length > 0 && w.networks.every((n) => n === "road");
