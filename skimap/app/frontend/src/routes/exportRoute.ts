import type { Feature, FeatureCollection } from "geojson";

import { ratingOf, overallOf, problemOf, shelfOf } from "../crux/assessment";
import { cruxTitle, dangerName } from "../dangerClasses";
import type { CruxEntry, LatLng } from "../types";
import type { Route } from "./routeList";
import { markerPositionOf } from "./snap";

/** A Crux as it goes out with its Route: a point where its marker stands,
 *  named the way the list names it, with what the user made of it. Only the
 *  ones still in play - kept or not yet decided - go out. */
type ExportedCrux = { at: LatLng; name: string; description: string; crux: CruxEntry };

const exportedCruxes = (route: Route): ExportedCrux[] =>
  route.cruxes
    .filter((crux) => shelfOf(crux) === "active")
    .map((crux) => {
      const rating = overallOf(crux);
      const parts = [
        dangerName(crux),
        crux.max_slope_deg !== undefined ? `max ${Math.round(crux.max_slope_deg)}°` : null,
        rating ? `assessed: ${ratingOf(rating).label}` : null,
      ];
      return {
        at: markerPositionOf(route.line, crux),
        name: `${crux.number}. ${cruxTitle(crux)}`,
        description: parts.filter(Boolean).join(", "),
        crux,
      };
    });

const escapeXml = (text: string): string =>
  text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");

/** The Route as GPX 1.1 - what GPS watches and phone apps read: the line as
 *  one track, in the direction it is travelled, and each Crux in play as a
 *  waypoint. Heights go along where the line has them. */
export const toGpx = (route: Route): string => {
  const name = escapeXml(route.name);
  const waypoints = exportedCruxes(route).map(
    ({ at, name: wptName, description }) =>
      `  <wpt lat="${at.lat}" lon="${at.lng}">\n` +
      `    <name>${escapeXml(wptName)}</name>\n` +
      `    <desc>${escapeXml(description)}</desc>\n` +
      `    <sym>Danger Area</sym>\n` +
      `  </wpt>\n`
  );
  const points = route.line.coordinates.map(([lng, lat, ele]) =>
    ele === undefined
      ? `      <trkpt lat="${lat}" lon="${lng}"/>\n`
      : `      <trkpt lat="${lat}" lon="${lng}"><ele>${ele}</ele></trkpt>\n`
  );
  return (
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<gpx version="1.1" creator="Skimap" xmlns="http://www.topografix.com/GPX/1/1">\n` +
    `  <metadata><name>${name}</name></metadata>\n` +
    waypoints.join("") +
    `  <trk>\n    <name>${name}</name>\n    <trkseg>\n` +
    points.join("") +
    `    </trkseg>\n  </trk>\n</gpx>\n`
  );
};

/** The Route as GeoJSON, for GIS tools: the line as one feature, and each
 *  Crux in play as a point with what the user made of it. */
export const toGeoJson = (route: Route): string => {
  const cruxes = exportedCruxes(route).map(
    ({ at, name, description, crux }): Feature => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [at.lng, at.lat] },
      properties: {
        number: crux.number,
        name,
        description,
        symbol: problemOf(crux),
        overall: overallOf(crux) ?? null,
        kept: crux.keep === true,
        distance_m: Math.round(crux.distance_m),
      },
    })
  );
  const collection: FeatureCollection = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: route.line,
        properties: { name: route.name, length_m: Math.round(route.lengthM) },
      },
      ...cruxes,
    ],
  };
  return JSON.stringify(collection, null, 2);
};

/** A file name for the Route: its name, without an extension an uploaded
 *  file brought along and without characters a file system refuses. */
export const exportFileName = (route: Route, extension: "gpx" | "geojson"): string => {
  const base =
    route.name
      .replace(/\.(gpx|geojson|json)$/i, "")
      .replace(/[\\/:*?"<>|]+/g, "_")
      .trim() || "route";
  return `${base}.${extension}`;
};

/** Hand the browser a file to save. */
export const downloadText = (fileName: string, mimeType: string, text: string) => {
  const url = URL.createObjectURL(new Blob([text], { type: mimeType }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

/** Download a Route as GPX or GeoJSON. */
export const downloadRoute = (route: Route, format: "gpx" | "geojson") =>
  format === "gpx"
    ? downloadText(exportFileName(route, "gpx"), "application/gpx+xml", toGpx(route))
    : downloadText(exportFileName(route, "geojson"), "application/geo+json", toGeoJson(route));
