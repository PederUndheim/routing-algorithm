import type { Crux } from "../types";

/** Cruxes drawn as one marker, because their pills would otherwise overlap.
 *
 *  Zoomed out far enough, a route's markers pile up into an unreadable
 *  stack - a dense tour puts thirty of them inside a centimetre of screen.
 *  Clustering is not a separate display mode: markers merge exactly when
 *  they would collide and split the moment there is room, so zooming is the
 *  only control and nothing is ever hidden without saying so. */
export type CruxCluster = {
  /** In route order, never empty. A cluster of one is a plain Crux. */
  members: Crux[];
  /** Whose colour, marks and degrees the cluster is drawn with. */
  worst: Crux;
  /** Where it is drawn: the first member, where the route reaches it. */
  head: Crux;
};

/** A pill's box in absolute layer pixels - the coordinates `map.project`
 *  gives, which move with zoom but not with panning. */
type Box = { left: number; top: number; right: number; bottom: number };

/** How bad a Crux is, for picking the one a cluster is drawn as. Steep
 *  ground that turns out to be a release area or a fall hazard beats plain
 *  steep ground, which beats a runout - the same order the line is
 *  coloured in. */
const severity = (crux: Crux): number => {
  if (crux.class !== "steep_slope") return 0;
  return crux.probable_release_area || crux.fall_hazard ? 2 : 1;
};

/** The worst of them, and the steepest where two are equally bad. Ties
 *  after that go to the earlier one, so the answer does not depend on the
 *  order the reduce happens to see them in. */
const worstOf = (members: readonly Crux[]): Crux =>
  members.reduce((worst, crux) => {
    const bySeverity = severity(crux) - severity(worst);
    if (bySeverity !== 0) return bySeverity > 0 ? crux : worst;
    return (crux.max_slope_deg ?? 0) > (worst.max_slope_deg ?? 0) ? crux : worst;
  });

const overlaps = (a: Box, b: Box, padding: number): boolean =>
  a.left - padding < b.right &&
  b.left - padding < a.right &&
  a.top - padding < b.bottom &&
  b.top - padding < a.bottom;

const union = (a: Box, b: Box): Box => ({
  left: Math.min(a.left, b.left),
  top: Math.min(a.top, b.top),
  right: Math.max(a.right, b.right),
  bottom: Math.max(a.bottom, b.bottom),
});

/** One route's Cruxes grouped into what can actually be drawn.
 *
 *  Walks them in route order and keeps adding to the current cluster while
 *  the next pill touches the box of everything in it so far. Growing
 *  against the cluster's whole box rather than only the last member is what
 *  stops one long chain of just-touching markers swallowing a route: a
 *  cluster spreads until it stops touching, then a new one starts.
 *
 *  `project` and `size` are passed in so this stays a function of numbers -
 *  Leaflet is the caller's business, and this is the part worth testing.
 */
export const clusterCruxes = (
  cruxes: readonly Crux[],
  project: (crux: Crux) => { x: number; y: number },
  size: (crux: Crux) => readonly [number, number],
  padding = 2
): CruxCluster[] => {
  const boxOf = (crux: Crux): Box => {
    const { x, y } = project(crux);
    const [width, height] = size(crux);
    // The pill is anchored by its number disc, which sits at its left end,
    // so it reaches right from the point and is centred on it vertically.
    return {
      left: x - height / 2,
      top: y - height / 2,
      right: x - height / 2 + width,
      bottom: y + height / 2,
    };
  };

  const groups: Crux[][] = [];
  let box: Box | null = null;
  for (const crux of cruxes) {
    const next = boxOf(crux);
    if (box && overlaps(box, next, padding)) {
      groups[groups.length - 1].push(crux);
      box = union(box, next);
    } else {
      groups.push([crux]);
      box = next;
    }
  }
  return groups.map((members) => ({
    members,
    worst: worstOf(members),
    head: members[0],
  }));
};

/** What a cluster's marker is numbered: the one Crux it holds, or the span
 *  it covers. The numbers run along the route, so a span says both which
 *  ones are in there and how many. */
export const clusterLabel = (cluster: CruxCluster): string => {
  const { members } = cluster;
  return members.length === 1
    ? `${members[0].number}`
    : `${members[0].number}-${members[members.length - 1].number}`;
};
