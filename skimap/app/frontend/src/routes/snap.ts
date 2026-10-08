import type { LineString, Position } from "geojson";

import type { LatLng } from "../types";
import { geodesicLength } from "./routeList";

const EARTH_RADIUS_M = 6_371_008.8;

/** The point on a line nearest to `point`, and how far along the line it
 *  is in metres.
 *
 *  Each segment is measured in a flat projection centred on it - fine at the
 *  scale of one segment - and the distance along is the same great-circle
 *  sum the rest of the app measures a Route with. */
export const nearestOnLine = (
  line: LineString,
  point: LatLng
): { position: LatLng; distance_m: number } => {
  const coords = line.coordinates;
  if (coords.length === 1) {
    return { position: { lat: coords[0][1], lng: coords[0][0] }, distance_m: 0 };
  }

  const rad = Math.PI / 180;
  let best = { d2: Infinity, position: point, distance_m: 0 };
  let along = 0;

  for (let i = 1; i < coords.length; i++) {
    const [lng1, lat1] = coords[i - 1];
    const [lng2, lat2] = coords[i];
    // Metres per degree here: x shrinks with latitude, y does not.
    const kx = Math.cos(((lat1 + lat2) / 2) * rad) * rad * EARTH_RADIUS_M;
    const ky = rad * EARTH_RADIUS_M;

    const bx = (lng2 - lng1) * kx;
    const by = (lat2 - lat1) * ky;
    const px = (point.lng - lng1) * kx;
    const py = (point.lat - lat1) * ky;

    const len2 = bx * bx + by * by;
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, (px * bx + py * by) / len2));
    const d2 = (px - t * bx) ** 2 + (py - t * by) ** 2;
    const segment = geodesicLength([coords[i - 1], coords[i]]);

    if (d2 < best.d2) {
      best = {
        d2,
        position: { lat: lat1 + t * (lat2 - lat1), lng: lng1 + t * (lng2 - lng1) },
        distance_m: along + t * segment,
      };
    }
    along += segment;
  }

  return { position: best.position, distance_m: best.distance_m };
};

/** The point on a line `distance_m` along it, clamped to its two ends. */
export const pointAtDistance = (line: LineString, distance_m: number): LatLng => {
  const coords = line.coordinates;
  let remaining = Math.max(distance_m, 0);

  for (let i = 1; i < coords.length; i++) {
    const segment = geodesicLength([coords[i - 1], coords[i]]);
    if (remaining <= segment && segment > 0) {
      const t = remaining / segment;
      return {
        lat: coords[i - 1][1] + t * (coords[i][1] - coords[i - 1][1]),
        lng: coords[i - 1][0] + t * (coords[i][0] - coords[i - 1][0]),
      };
    }
    remaining -= segment;
  }

  const last = coords[coords.length - 1];
  return { lat: last[1], lng: last[0] };
};

/** The stretch of a line between two distances along it, as GeoJSON
 *  coordinates, both ends clamped to the line. Fewer than two points when
 *  there is nothing between them. */
export const sliceLine = (line: LineString, from_m: number, to_m: number): Position[] => {
  const coords = line.coordinates;
  const out: Position[] = [];
  if (to_m <= from_m) return out;

  let along = 0;
  for (let i = 1; i < coords.length; i++) {
    const segment = geodesicLength([coords[i - 1], coords[i]]);
    const start = along;
    const end = along + segment;
    along = end;
    if (segment === 0 || end <= from_m) continue;
    if (start >= to_m) break;

    const at = (d: number): Position => {
      const t = (d - start) / segment;
      return [
        coords[i - 1][0] + t * (coords[i][0] - coords[i - 1][0]),
        coords[i - 1][1] + t * (coords[i][1] - coords[i - 1][1]),
      ];
    };
    if (out.length === 0) out.push(at(Math.max(from_m, start)));
    out.push(to_m < end ? at(to_m) : coords[i]);
  }
  return out;
};

/** How far before an identified Crux its marker is drawn, so it is seen in
 *  time to weigh up the danger before walking into it. A Crux the user has
 *  placed or moved is marked exactly where they put it. */
export const MARKER_LEAD_M = 30;

/** Where an identified Crux's marker goes: `MARKER_LEAD_M` back along the
 *  line from the Crux, or the start of the line if the Crux is closer than
 *  that to it. Measured from the Crux's own position rather than its
 *  `distance_m`, which the backend counts on a different grid than the line
 *  is measured on here. */
export const markerSpot = (line: LineString, crux: LatLng): LatLng =>
  pointAtDistance(line, nearestOnLine(line, crux).distance_m - MARKER_LEAD_M);
