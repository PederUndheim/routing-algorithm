// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import type { CruxResult, RouteResponse } from "../types";
import { createRouteList } from "./routeList";
import type { RouteList } from "./routeList";

const routed = (): RouteResponse => ({
  route: {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: {
          type: "LineString",
          coordinates: [
            [7.8, 62.6],
            [7.9, 62.65],
          ],
        },
      },
    ],
  },
  corridor: {
    png_path: "/corridor/0123456789ab.png",
    bounds: { west: 7.7, south: 62.5, east: 8.0, north: 62.7 },
  },
  length_m: 6200,
  straight_m: 5000,
  detour: 1.24,
  cost: 1234,
  seconds: 3.1,
});

const names = (list: RouteList) => list.getState().routes.map((r) => r.name);

const selectedName = (list: RouteList) => {
  const { routes, selectedId } = list.getState();
  return routes.find((r) => r.id === selectedId)?.name ?? null;
};

describe("routed Routes", () => {
  it("are named Route 1, Route 2 and the newest becomes the Selected route", () => {
    const list = createRouteList();

    list.addRouted(routed());
    list.addRouted(routed());

    expect(names(list)).toEqual(["Route 1", "Route 2"]);
    expect(selectedName(list)).toBe("Route 2");
  });
});

const file = (name: string, content: string) => new File([content], name);

const gpx = (body: string) =>
  `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">${body}</gpx>`;

describe("uploading GPX", () => {
  it("makes a track one uploaded Route named after its file, segments joined in order", async () => {
    const list = createRouteList();

    const { errors } = await list.upload([
      file(
        "tour.gpx",
        gpx(`
          <wpt lat="62.0" lon="7.0"><name>Hut</name></wpt>
          <trk>
            <name>Up</name>
            <trkseg>
              <trkpt lat="62.60" lon="7.80"><ele>100</ele><time>2026-01-01T10:00:00Z</time></trkpt>
              <trkpt lat="62.61" lon="7.81"><ele>180</ele></trkpt>
            </trkseg>
            <trkseg>
              <trkpt lat="62.62" lon="7.82"/>
            </trkseg>
          </trk>`)
      ),
    ]);

    expect(errors).toEqual([]);
    const [route] = list.getState().routes;
    expect(route.name).toBe("tour.gpx");
    expect(route.source).toBe("uploaded");
    expect(route.line.coordinates).toEqual([
      [7.8, 62.6],
      [7.81, 62.61],
      [7.82, 62.62],
    ]);
    expect(selectedName(list)).toBe("tour.gpx");
  });

  it("makes one Route per track and per <rte>, in file order, the last one selected", async () => {
    const list = createRouteList();

    await list.upload([
      file(
        "tour.gpx",
        gpx(`
          <trk><trkseg><trkpt lat="62.60" lon="7.80"/><trkpt lat="62.61" lon="7.81"/></trkseg></trk>
          <rte><rtept lat="61.00" lon="8.00"/><rtept lat="61.01" lon="8.01"/></rte>
          <trk><trkseg><trkpt lat="60.00" lon="9.00"/><trkpt lat="60.01" lon="9.01"/></trkseg></trk>`)
      ),
    ]);

    const { routes } = list.getState();
    expect(routes.map((r) => r.name)).toEqual(["tour.gpx", "tour.gpx (2)", "tour.gpx (3)"]);
    expect(routes.map((r) => r.line.coordinates[0])).toEqual([
      [7.8, 62.6],
      [8.0, 61.0],
      [9.0, 60.0],
    ]);
    expect(selectedName(list)).toBe("tour.gpx (3)");
  });
});

describe("uploading GeoJSON", () => {
  it("makes one Route per line in a FeatureCollection, MultiLineString parts joined, points skipped", async () => {
    const list = createRouteList();

    const { errors } = await list.upload([
      file(
        "lines.geojson",
        JSON.stringify({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              properties: {},
              geometry: { type: "Point", coordinates: [7.0, 62.0] },
            },
            {
              type: "Feature",
              properties: {},
              geometry: {
                type: "LineString",
                coordinates: [
                  [7.8, 62.6, 120],
                  [7.81, 62.61, 150],
                ],
              },
            },
            {
              type: "Feature",
              properties: {},
              geometry: {
                type: "MultiLineString",
                coordinates: [
                  [
                    [8.0, 61.0],
                    [8.01, 61.01],
                  ],
                  [[8.02, 61.02]],
                ],
              },
            },
          ],
        })
      ),
    ]);

    expect(errors).toEqual([]);
    const { routes } = list.getState();
    expect(routes.map((r) => r.name)).toEqual(["lines.geojson", "lines.geojson (2)"]);
    expect(routes.map((r) => r.line.coordinates)).toEqual([
      [
        [7.8, 62.6],
        [7.81, 62.61],
      ],
      [
        [8.0, 61.0],
        [8.01, 61.01],
        [8.02, 61.02],
      ],
    ]);
  });
});

describe("uploading GeoJSON shapes", () => {
  it("accepts a single Feature and a bare geometry as well", async () => {
    const list = createRouteList();
    const line = {
      type: "LineString",
      coordinates: [
        [7.8, 62.6],
        [7.81, 62.61],
      ],
    };

    const { errors } = await list.upload([
      file("feature.json", JSON.stringify({ type: "Feature", properties: {}, geometry: line })),
      file("bare.geojson", JSON.stringify(line)),
    ]);

    expect(errors).toEqual([]);
    expect(names(list)).toEqual(["feature.json", "bare.geojson"]);
  });
});

describe("uploading a bad file", () => {
  it("reports it by name and reason, and still loads the other files", async () => {
    const list = createRouteList();

    const { errors } = await list.upload([
      file("broken.geojson", "{ not json"),
      file("waypoints.gpx", gpx(`<wpt lat="62.0" lon="7.0"/>`)),
      file(
        "good.gpx",
        gpx(`<trk><trkseg><trkpt lat="62.60" lon="7.80"/><trkpt lat="62.61" lon="7.81"/></trkseg></trk>`)
      ),
    ]);

    expect(names(list)).toEqual(["good.gpx"]);
    expect(selectedName(list)).toBe("good.gpx");
    expect(errors).toEqual([
      { fileName: "broken.geojson", reason: "not valid JSON" },
      { fileName: "waypoints.gpx", reason: "holds no lines" },
    ]);
  });

  it("rejects a GeoJSON in projected coordinates rather than place it wrong", async () => {
    const list = createRouteList();

    const { errors } = await list.upload([
      file(
        "utm.geojson",
        JSON.stringify({
          type: "LineString",
          coordinates: [
            [136157.9, 6964433.6],
            [136210.0, 6964480.2],
          ],
        })
      ),
    ]);

    expect(errors).toEqual([{ fileName: "utm.geojson", reason: "must be WGS84 (lat/lon)" }]);
    expect(names(list)).toEqual([]);
  });

  it("reports a GPX point without coordinates rather than put it at 0, 0", async () => {
    const list = createRouteList();

    const { errors } = await list.upload([
      file(
        "gap.gpx",
        gpx(`<trk><trkseg><trkpt lat="62.60" lon="7.80"/><trkpt lat="62.61"/></trkseg></trk>`)
      ),
    ]);

    expect(errors).toEqual([
      { fileName: "gap.gpx", reason: "has a point without a numeric lat/lon" },
    ]);
    expect(names(list)).toEqual([]);
  });
});

const cruxResult = (distance: number): CruxResult => ({
  segments: [
    {
      class: "fall_hazard",
      start_m: 0,
      end_m: 6200,
      line: {
        type: "LineString",
        coordinates: [
          [7.8, 62.6],
          [7.9, 62.65],
        ],
      },
    },
  ],
  cruxes: [
    {
      number: 1,
      class: "fall_hazard",
      position: { lat: 62.6, lng: 7.8 },
      distance_m: distance,
      length_m: 6200,
    },
  ],
  length_m: 6200,
  no_data_m: 0,
});

describe("a crux result", () => {
  it("belongs to its own Route and replaces the one that Route had", () => {
    const list = createRouteList();
    const first = list.addRouted(routed());
    list.addRouted(routed());

    list.attachCrux(first.id, cruxResult(40));
    list.attachCrux(first.id, cruxResult(90));

    const [analysed, other] = list.getState().routes;
    expect(analysed.crux?.cruxes.map((c) => c.distance_m)).toEqual([90]);
    expect(other.crux).toBeNull();
    expect(selectedName(list)).toBe("Route 2");
  });

  it("makes the Route it was identified on visible again", () => {
    const list = createRouteList();
    const route = list.addRouted(routed());
    list.toggleVisible(route.id);

    list.attachCrux(route.id, cruxResult(40));

    expect(list.getState().routes[0].visible).toBe(true);
  });

  it("is dropped when its Route was deleted while it was being identified", () => {
    const list = createRouteList();
    const route = list.addRouted(routed());
    list.remove(route.id);

    list.attachCrux(route.id, cruxResult(40));

    expect(list.getState().routes).toEqual([]);
  });
});

describe("hiding", () => {
  it("the Selected route keeps it selected, and showing it again brings it back", () => {
    const list = createRouteList();
    const route = list.addRouted(routed());

    list.toggleVisible(route.id);
    expect(list.getState().routes[0].visible).toBe(false);
    expect(selectedName(list)).toBe("Route 1");

    list.toggleVisible(route.id);
    expect(list.getState().routes[0].visible).toBe(true);
  });
});

describe("deleting", () => {
  it("the Selected route selects the one above it, and nothing once the list is empty", () => {
    const list = createRouteList();
    list.addRouted(routed());
    list.addRouted(routed());
    const third = list.addRouted(routed());

    list.remove(third.id);
    expect(names(list)).toEqual(["Route 1", "Route 2"]);
    expect(selectedName(list)).toBe("Route 2");

    list.remove(list.getState().selectedId!);
    list.remove(list.getState().selectedId!);
    expect(names(list)).toEqual([]);
    expect(list.getState().selectedId).toBeNull();
  });

  it("the top Route while it is selected selects the one that moves up into its place", () => {
    const list = createRouteList();
    const first = list.addRouted(routed());
    list.addRouted(routed());
    list.select(first.id);

    list.remove(first.id);

    expect(selectedName(list)).toBe("Route 2");
  });

  it("a Route that is not selected leaves the selection alone", () => {
    const list = createRouteList();
    const first = list.addRouted(routed());
    list.addRouted(routed());

    list.remove(first.id);

    expect(selectedName(list)).toBe("Route 2");
  });
});
