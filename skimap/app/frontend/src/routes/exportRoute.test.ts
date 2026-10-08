import { describe, expect, it } from "vitest";

import { exportFileName, toGeoJson, toGpx } from "./exportRoute";
import { createRouteList } from "./routeList";

const routeWithCruxes = () => {
  const list = createRouteList();
  const route = list.addDrawn([
    [7.8, 62.6],
    [7.81, 62.6],
    [7.81, 62.61],
  ]);
  const place = (distance_m: number, description: string) =>
    list.addManualCrux(route.id, {
      position: { lat: 62.6, lng: 7.805 },
      distance_m,
      problem: "release_area",
      color: "#D32F2F",
      description,
      length_m: 0,
    })!;
  const kept = place(100, "Lip <under> the ridge & cornice");
  list.setOverall(route.id, kept.id, "very_bad");
  list.setKeep(route.id, kept.id, true);
  const removed = place(200, "Not this one");
  list.setKeep(route.id, removed.id, false);
  return list.getState().routes[0];
};

describe("exporting a route", () => {
  it("writes GPX with the line as a track and the cruxes in play as waypoints", () => {
    const gpx = toGpx(routeWithCruxes());
    expect(gpx).toContain('<gpx version="1.1"');
    expect(gpx.match(/<trkpt /g)).toHaveLength(3);
    expect(gpx.match(/<wpt /g)).toHaveLength(1);
    // Escaped, and the user's verdict along with it.
    expect(gpx).toContain("1. Lip &lt;under&gt; the ridge &amp; cornice");
    expect(gpx).toContain("assessed: Very negative");
    expect(gpx).not.toContain("Not this one");
  });

  it("writes GeoJSON with the line and a point per crux in play", () => {
    const collection = JSON.parse(toGeoJson(routeWithCruxes()));
    expect(collection.features.map((f: { geometry: { type: string } }) => f.geometry.type)).toEqual([
      "LineString",
      "Point",
    ]);
    expect(collection.features[1].properties).toMatchObject({
      number: 1,
      symbol: "release_area",
      overall: "very_bad",
      kept: true,
    });
  });

  it("names the file after the route, without an uploaded file's extension", () => {
    const route = { ...routeWithCruxes(), name: "Romsdalshorn: tour.gpx" };
    expect(exportFileName(route, "gpx")).toBe("Romsdalshorn_ tour.gpx");
    expect(exportFileName(route, "geojson")).toBe("Romsdalshorn_ tour.geojson");
  });
});
