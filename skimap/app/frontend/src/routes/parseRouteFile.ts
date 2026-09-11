import type { Position } from "geojson";

/** Why a file could not be used. The message is worded to follow the file
 *  name: "tour.gpx: holds no lines". */
export class RouteFileError extends Error {}

/** The lines in one uploaded file, each as WGS84 [lng, lat] positions.
 *
 * Only the route list's upload action calls this; it is a file of its own
 * because GPX and GeoJSON each take some reading, not because anything else
 * should parse routes. Throws RouteFileError for a file that yields no line
 * of at least two points - a lone point is not something to walk along.
 */
export const parseRouteFile = (fileName: string, text: string): Position[][] => {
  const parsed = isGpx(fileName, text) ? parseGpx(text) : parseGeoJson(text);

  // Any one coordinate out of range rejects the whole file. A GeoJSON in
  // UTM would otherwise not fail - it would land somewhere else entirely.
  for (const [lng, lat] of parsed.flat()) {
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
      throw new RouteFileError("has a point without a numeric lat/lon");
    }
    if (Math.abs(lng) > 180 || Math.abs(lat) > 90) {
      throw new RouteFileError("must be WGS84 (lat/lon)");
    }
  }

  const lines = parsed.filter((line) => line.length >= 2);
  if (lines.length === 0) throw new RouteFileError("holds no lines");
  return lines;
};

/** By extension where there is a telling one, else by the first character:
 *  GPX is XML, GeoJSON is a JSON object. */
const isGpx = (fileName: string, text: string): boolean => {
  const name = fileName.toLowerCase();
  if (name.endsWith(".gpx")) return true;
  if (name.endsWith(".geojson") || name.endsWith(".json")) return false;
  return text.trimStart().startsWith("<");
};

/** One line per <trk> and per <rte>, in file order. A track's segments are
 *  joined in order. Waypoints, elevation and time are ignored: only the
 *  points' lat/lon matter here. */
const parseGpx = (text: string): Position[][] => {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  // The XML parser does not throw; it hands back a document holding this.
  if (doc.getElementsByTagName("parsererror").length > 0) {
    throw new RouteFileError("not valid GPX");
  }

  // By local name, in any namespace: GPX 1.0 and 1.1 declare different
  // ones, and some exporters prefix the elements rather than set a default.
  return Array.from(doc.documentElement.children)
    .filter((el) => el.localName === "trk" || el.localName === "rte")
    .map((el) => {
      const point = el.localName === "trk" ? "trkpt" : "rtept";
      return Array.from(el.getElementsByTagNameNS("*", point)).map(gpxPoint);
    });
};

const gpxPoint = (el: Element): Position => [
  gpxCoordinate(el.getAttribute("lon")),
  gpxCoordinate(el.getAttribute("lat")),
];

/** NaN for a missing or empty attribute, where Number() would say 0 - and
 *  0, 0 is a valid WGS84 point, off the coast of Africa. */
const gpxCoordinate = (value: string | null): number =>
  value === null || value.trim() === "" ? NaN : Number(value);

/** Loose on purpose: an uploaded file is whatever someone saved, not
 *  something the geojson types can vouch for. */
type GeoJsonish = {
  type?: unknown;
  features?: unknown;
  geometry?: unknown;
  coordinates?: unknown;
};

const isObject = (value: unknown): value is GeoJsonish =>
  typeof value === "object" && value !== null;

/** One line per LineString and per MultiLineString, the latter's parts
 *  joined in order. A FeatureCollection, a single Feature and a bare
 *  geometry are all accepted; any other geometry type is skipped. */
const parseGeoJson = (text: string): Position[][] => {
  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch {
    throw new RouteFileError("not valid JSON");
  }
  return geometriesOf(json).flatMap(linesOf);
};

const geometriesOf = (json: unknown): GeoJsonish[] => {
  if (!isObject(json)) return [];
  switch (json.type) {
    case "FeatureCollection":
      return Array.isArray(json.features) ? json.features.flatMap(geometriesOf) : [];
    case "Feature":
      return isObject(json.geometry) ? [json.geometry] : [];
    default:
      return [json];
  }
};

const linesOf = (geometry: GeoJsonish): Position[][] => {
  const coordinates = Array.isArray(geometry.coordinates) ? geometry.coordinates : [];
  switch (geometry.type) {
    case "LineString":
      return [(coordinates as Position[]).map(lngLat)];
    case "MultiLineString":
      return [(coordinates as Position[][]).flat().map(lngLat)];
    default:
      return [];
  }
};

/** Drops elevation, and anything else past the first two. */
const lngLat = ([lng, lat]: Position): Position => [lng, lat];
