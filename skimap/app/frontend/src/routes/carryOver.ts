import type { LineString, Position } from "geojson";

import type { CruxEntry, CruxResult, CruxSegment, Extent, LatLng } from "../types";
import { geodesicLength } from "./routeList";
import { nearestOnLine, pointAtDistance, sliceLine } from "./snap";

/** How far a point of the old line may lie from the new one and still be
 *  ground the edit left alone. Tight: an untouched stretch is put back
 *  exactly as it was (see restoreUnedited), so only an edit moves it. */
export const ON_LINE_M = 5;

/** How closely the old line is checked against the new one. */
const SAMPLE_M = 10;

const metresBetween = (a: LatLng, b: LatLng): number =>
  geodesicLength([
    [a.lng, a.lat],
    [b.lng, b.lat],
  ]);

/** Points along a stretch, every SAMPLE_M and at both ends. */
const samplesAlong = (coords: readonly Position[]): LatLng[] => {
  const out: LatLng[] = [{ lat: coords[0][1], lng: coords[0][0] }];
  let carried = 0;
  for (let i = 1; i < coords.length; i++) {
    const [lng1, lat1] = coords[i - 1];
    const [lng2, lat2] = coords[i];
    const segment = geodesicLength([coords[i - 1], coords[i]]);
    let at = SAMPLE_M - carried;
    while (at < segment) {
      const t = at / segment;
      out.push({ lat: lat1 + t * (lat2 - lat1), lng: lng1 + t * (lng2 - lng1) });
      at += SAMPLE_M;
    }
    carried = segment - (at - SAMPLE_M);
  }
  const last = coords[coords.length - 1];
  out.push({ lat: last[1], lng: last[0] });
  return out;
};

/** Each sample of a stretch of the old line, and where it lands on the new
 *  one - or null where the edit moved it off. Landing further back than
 *  the sample before it is off too: the new line has to run the same way. */
const landings = (oldLine: LineString, newLine: LineString, extent: Extent): (number | null)[] => {
  const coords = sliceLine(oldLine, extent.start_m, extent.end_m);
  const samples =
    coords.length >= 2 ? samplesAlong(coords) : [pointAtDistance(oldLine, extent.start_m)];
  let last = -Infinity;
  return samples.map((p) => {
    const near = nearestOnLine(newLine, p);
    if (metresBetween(p, near.position) > ON_LINE_M || near.distance_m < last - ON_LINE_M) {
      return null;
    }
    last = near.distance_m;
    return near.distance_m;
  });
};

/** Where a stretch of the old line is on the new one, if the edit left all
 *  of it alone; null if any of it was moved. */
export const remapStretch = (
  oldLine: LineString,
  newLine: LineString,
  extent: Extent
): Extent | null => {
  const at = landings(oldLine, newLine, extent);
  if (at.some((d) => d === null)) return null;
  return { start_m: at[0]!, end_m: Math.max(at[0]!, at[at.length - 1]!) };
};

/** The parts of a stretch of the old line the edit left alone, where they
 *  are on the new one. */
const remapParts = (oldLine: LineString, newLine: LineString, extent: Extent): Extent[] => {
  const parts: Extent[] = [];
  let run: Extent | null = null;
  for (const d of landings(oldLine, newLine, extent)) {
    if (d === null) {
      if (run) parts.push(run);
      run = null;
    } else if (run) run.end_m = d;
    else run = { start_m: d, end_m: d };
  }
  if (run) parts.push(run);
  return parts.filter((p) => p.end_m - p.start_m >= 1);
};

/** A Crux snapped onto the new line, where its marker goes now. */
const snapped = (crux: CruxEntry, newLine: LineString): CruxEntry => {
  const near = nearestOnLine(newLine, crux.position);
  return { ...crux, position: near.position, distance_m: near.distance_m };
};

/** What of a Route's analysis and Cruxes holds on its edited line.
 *
 *  Wherever the edit left the line alone, the colours and every Crux on it
 *  stay, with all the user has made of them, moved along to where that
 *  ground now is on the line. An identified Crux any of whose ground was
 *  changed is gone: what was assessed is not there any more. One placed by
 *  hand stays - it was put there on purpose - snapped onto the new line,
 *  keeping as much of its stretch as it can. The changed ground is left
 *  unanalysed: `unanalysed_m` says how much, for Update cruxes to fill. */
export const carryOverEdit = (
  oldLine: LineString,
  newLine: LineString,
  crux: CruxResult | null,
  cruxes: readonly CruxEntry[]
): { crux: CruxResult | null; cruxes: CruxEntry[]; unanalysed_m: number } => {
  const oldLength = geodesicLength(oldLine.coordinates);
  const newLength = geodesicLength(newLine.coordinates);

  let kept: CruxResult | null = null;
  let unanalysed_m = 0;
  if (crux) {
    // The backend measures on its own grid; these are this line's metres.
    const scale = crux.length_m > 0 ? oldLength / crux.length_m : 1;
    const segments: CruxSegment[] = crux.segments.flatMap((segment) =>
      remapParts(oldLine, newLine, {
        start_m: segment.start_m * scale,
        end_m: segment.end_m * scale,
      }).map((part) => ({
        ...segment,
        ...part,
        line: { type: "LineString", coordinates: sliceLine(newLine, part.start_m, part.end_m) },
      }))
    );
    const covered = segments.reduce((sum, s) => sum + s.end_m - s.start_m, 0);
    const noData = segments
      .filter((s) => s.class === "no_data")
      .reduce((sum, s) => sum + s.end_m - s.start_m, 0);
    kept = {
      ...crux,
      segments,
      // Now on this line's own measure, so scale comes out at 1 from here.
      length_m: newLength,
      no_data_m: noData,
    };
    unanalysed_m = Math.max(newLength - covered, 0);
  }

  const carried = cruxes.flatMap((c): CruxEntry[] => {
    const area = c.area ? remapStretch(oldLine, newLine, c.area) : undefined;
    const extent = c.extent ? remapStretch(oldLine, newLine, c.extent) : undefined;

    if (c.source === "identified") {
      if (area === null || extent === null) return [];
      return [
        {
          ...snapped(c, newLine),
          ...(area ? { area } : {}),
          ...(extent ? { extent } : {}),
        },
      ];
    }

    const moved = snapped(c, newLine);
    if (!c.extent) return [moved];
    // Its stretch kept where it can be; else as long as it was, from the
    // marker's new place.
    const length = c.extent.end_m - c.extent.start_m;
    return [
      {
        ...moved,
        extent: extent ?? {
          start_m: moved.distance_m,
          end_m: Math.min(moved.distance_m + length, newLength),
        },
      },
    ];
  });

  return { crux: kept, cruxes: carried, unanalysed_m };
};

/** How much two stretches share, against the shorter of them. */
const overlap = (a: Extent, b: Extent): number => {
  const shared = Math.min(a.end_m, b.end_m) - Math.max(a.start_m, b.start_m);
  const shorter = Math.min(a.end_m - a.start_m, b.end_m - b.start_m);
  if (shorter <= 0) return Math.abs(a.start_m - b.start_m) < SAMPLE_M ? 1 : 0;
  return Math.max(shared, 0) / shorter;
};

/** Enough of the same ground that a Crux found again is the same Crux. */
const SAME_CRUX = 0.5;

/** Update cruxes: the identified Cruxes a new analysis found, each paired
 *  with the one already there for the same ground, so what the user made
 *  of it carries over.
 *
 *  A Crux found again keeps its id - and, if the user had made anything of
 *  it, everything they made: ratings, kept or not, deleted, its symbol and
 *  words, a moved marker, an edited stretch. Only the area the analysis
 *  measured is the new one. One found for the first time comes in fresh.
 *  An old one not found again goes, unless the user had worked on it: that
 *  work is theirs and stays until they delete it. */
export const mergeIdentified = (
  previous: readonly CruxEntry[],
  found: readonly CruxEntry[],
  isEdited: (crux: CruxEntry) => boolean
): CruxEntry[] => {
  const unmatched = new Set(previous.filter((c) => c.source === "identified"));
  const merged = found.map((fresh) => {
    let best: CruxEntry | null = null;
    let bestOverlap = SAME_CRUX;
    for (const old of unmatched) {
      if (!old.area || !fresh.area) continue;
      const shared = overlap(old.area, fresh.area);
      if (shared >= bestOverlap) {
        best = old;
        bestOverlap = shared;
      }
    }
    if (!best) return fresh;
    unmatched.delete(best);
    if (!isEdited(best) && best.color === undefined && best.description === undefined) {
      return { ...fresh, id: best.id };
    }
    return {
      ...best,
      area: fresh.area,
      ...(best.moved ? {} : { position: fresh.position, distance_m: fresh.distance_m }),
    };
  });
  return [...merged, ...[...unmatched].filter(isEdited)];
};
