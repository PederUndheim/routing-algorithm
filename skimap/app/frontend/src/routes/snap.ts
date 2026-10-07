import type { LineString } from "geojson";

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
