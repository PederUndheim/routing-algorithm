// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import type { CruxResult, RouteResponse } from "../types";
import { createRouteList, geodesicLength, isEdited } from "./routeList";
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
      class: "steep_slope",
      fall_hazard: true,
      max_slope_deg: 52,
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
      class: "steep_slope",
      fall_hazard: true,
      max_slope_deg: 52,
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

describe("drawn Routes", () => {
  const line = [
    [7.8, 62.6],
    [7.81, 62.6],
  ];

  it("are named Drawn route 1, 2, measured, and the newest becomes the Selected route", () => {
    const list = createRouteList();

    list.addRouted(routed());
    list.addDrawn(line);
    const second = list.addDrawn(line);

    expect(names(list)).toEqual(["Route 1", "Drawn route 1", "Drawn route 2"]);
    expect(selectedName(list)).toBe("Drawn route 2");
    expect(second.source).toBe("drawn");
    // 0.01 deg of longitude at 62.6 N is about 512 m.
    expect(second.lengthM).toBeGreaterThan(505);
    expect(second.lengthM).toBeLessThan(520);
  });

  it("edited get the new line and length, lose their stale crux result, and are shown", () => {
    const list = createRouteList();
    const route = list.addDrawn(line);
    list.attachCrux(route.id, cruxResult(40));
    list.toggleVisible(route.id);

    const longer = [...line, [7.82, 62.6]];
    list.updateLine(route.id, longer);

    const edited = list.getState().routes[0];
    expect(edited.line.coordinates).toEqual(longer);
    expect(edited.lengthM).toBeGreaterThan(route.lengthM * 1.9);
    expect(edited.crux).toBeNull();
    expect(edited.visible).toBe(true);
    expect(edited.name).toBe("Drawn route 1");
  });
});

describe("cruxes on a Route", () => {
  const manual = (distance: number) => ({
    position: { lat: 62.6, lng: 7.8 },
    distance_m: distance,
    category: "35_39" as const,
    problem: "release_area" as const,
    color: "#D32F2F",
    description: "  Wind-loaded lip  ",
    length_m: 150,
  });

  const cruxesOf = (list: RouteList) => list.getState().routes[0].cruxes;

  it("placed by hand fall into route order among the identified ones, numbered along it", () => {
    const list = createRouteList();
    const route = list.addRouted(routed());
    list.attachCrux(route.id, cruxResult(400));

    list.addManualCrux(route.id, manual(100));
    list.addManualCrux(route.id, manual(900));

    expect(cruxesOf(list).map((c) => [c.number, c.source, c.distance_m])).toEqual([
      [1, "manual", 100],
      [2, "identified", 400],
      [3, "manual", 900],
    ]);
    const first = cruxesOf(list)[0];
    expect(first.class).toBe("steep_slope");
    expect(first.probable_release_area).toBe(true);
    expect(first.description).toBe("Wind-loaded lip");
  });

  it("identified get their area on this line's measure, and re-identifying keeps the hand-placed ones", () => {
    const list = createRouteList();
    const route = list.addRouted(routed());
    list.attachCrux(route.id, cruxResult(400));
    list.addManualCrux(route.id, manual(100));

    // The backend called the line 6200 m; here it is measured great circle.
    const scale = geodesicLength(route.line.coordinates) / 6200;
    const { area } = cruxesOf(list)[1];
    expect(area!.start_m).toBeCloseTo(400 * scale, 6);
    expect(area!.end_m).toBeCloseTo(6600 * scale, 6);

    list.attachCrux(route.id, cruxResult(50));

    expect(cruxesOf(list).map((c) => [c.source, c.distance_m])).toEqual([
      ["identified", 50],
      ["manual", 100],
    ]);
  });

  it("keep their ratings, overall and keep choice, each of which can be taken back", () => {
    const list = createRouteList();
    const route = list.addRouted(routed());
    const crux = list.addManualCrux(route.id, manual(100))!;

    list.setAnswer(route.id, crux.id, "slope_size", "bad");
    list.setAnswer(route.id, crux.id, "safe_spots", "good");
    list.setAnswer(route.id, crux.id, "safe_spots", undefined);
    list.setOverall(route.id, crux.id, "neutral");
    list.setKeep(route.id, crux.id, false);
    expect(cruxesOf(list)[0]).toMatchObject({
      answers: { slope_size: "bad" },
      overall: "neutral",
      keep: false,
    });

    // Restored from the not-kept shelf: undecided again, ratings kept.
    list.restoreCrux(route.id, crux.id);
    list.setOverall(route.id, crux.id, undefined);
    expect(cruxesOf(list)[0].keep).toBeUndefined();
    expect(cruxesOf(list)[0].overall).toBeUndefined();
    expect(cruxesOf(list)[0].answers).toEqual({ slope_size: "bad" });
  });

  it("colour a stretch that is edited apart from the marker, and reset back", () => {
    const list = createRouteList();
    const route = list.addRouted(routed());
    list.attachCrux(route.id, cruxResult(400));
    const mine = list.addManualCrux(route.id, manual(100))!;
    expect(cruxesOf(list)[0].extent).toEqual({ start_m: 100, end_m: 250 });

    const identified = cruxesOf(list)[1];
    list.setExtent(route.id, identified.id, { start_m: 500, end_m: 700 });
    list.moveCrux(route.id, mine.id, { position: { lat: 62.61, lng: 7.81 }, distance_m: 900 });
    expect(cruxesOf(list).find((c) => c.id === identified.id)!.extent).toEqual({
      start_m: 500,
      end_m: 700,
    });
    // Moving the marker leaves the stretch where it was.
    expect(cruxesOf(list).find((c) => c.id === mine.id)!.extent).toEqual({
      start_m: 100,
      end_m: 250,
    });

    list.setExtent(route.id, identified.id, undefined);
    expect(cruxesOf(list).find((c) => c.id === identified.id)!.extent).toBeUndefined();

    // A marker taken along by an extent edit can be put back exactly,
    // unmoved again.
    const { position, distance_m } = identified;
    list.moveCrux(route.id, identified.id, { position: { lat: 62.62, lng: 7.84 }, distance_m: 2000 });
    list.setMarker(route.id, identified.id, { position, distance_m, moved: undefined });
    expect(cruxesOf(list).find((c) => c.id === identified.id)).toMatchObject({ position, distance_m });
    expect(cruxesOf(list).find((c) => c.id === identified.id)!.moved).toBeUndefined();
  });

  it("can be renamed, given another symbol and colour, and fall back to their symbol's", () => {
    const list = createRouteList();
    const route = list.addRouted(routed());
    list.attachCrux(route.id, cruxResult(400));
    const identified = cruxesOf(list)[0];
    expect(identified.fall_hazard).toBe(true);

    list.editCrux(route.id, identified.id, {
      description: "  Corniced ridge  ",
      problem: "runout_area",
      color: "#E65100",
    });
    const edited = cruxesOf(list)[0];
    expect(edited).toMatchObject({ class: "runout_area", description: "Corniced ridge", color: "#E65100" });
    expect(edited.fall_hazard).toBeUndefined();
    // What the analysis measured stays.
    expect(edited.max_slope_deg).toBe(52);

    // Its own symbol's name and colour are not stored, so they follow it.
    list.editCrux(route.id, identified.id, {
      description: "Runout area",
      problem: "runout_area",
      color: "#FFA726",
    });
    expect(cruxesOf(list)[0].description).toBeUndefined();
    expect(cruxesOf(list)[0].color).toBeUndefined();
  });

  it("count as worked on once the user has done anything to an identified one", () => {
    const list = createRouteList();
    const route = list.addRouted(routed());
    list.attachCrux(route.id, cruxResult(400));
    list.addManualCrux(route.id, manual(100));
    expect(cruxesOf(list).some(isEdited)).toBe(false);

    const identified = cruxesOf(list).find((c) => c.source === "identified")!;
    list.setOverall(route.id, identified.id, "good");
    expect(cruxesOf(list).some(isEdited)).toBe(true);
  });

  it("can be moved along the Route, keeping their answers and renumbering to the new order", () => {
    const list = createRouteList();
    const route = list.addRouted(routed());
    list.attachCrux(route.id, cruxResult(400));
    const mine = list.addManualCrux(route.id, manual(100))!;
    list.setAnswer(route.id, mine.id, "slope_size", "bad");
    const spot = { position: { lat: 62.61, lng: 7.81 }, distance_m: 900 };

    list.moveCrux(route.id, mine.id, spot);

    expect(cruxesOf(list).map((c) => [c.number, c.source, c.distance_m])).toEqual([
      [1, "identified", 400],
      [2, "manual", 900],
    ]);
    expect(cruxesOf(list)[1].position).toEqual(spot.position);
    expect(cruxesOf(list)[1].answers).toEqual({ slope_size: "bad" });
    // Moved by hand, so its marker stands on the spot; the one it was
    // placed beside is untouched.
    expect(cruxesOf(list)[1].moved).toBe(true);
    expect(cruxesOf(list)[0].moved).toBeUndefined();
  });

  it("can be deleted and brought back, and all go when the line is edited", () => {
    const list = createRouteList();
    const route = list.addDrawn([
      [7.8, 62.6],
      [7.81, 62.6],
    ]);
    const a = list.addManualCrux(route.id, manual(100))!;
    list.addManualCrux(route.id, manual(200));
    list.setAnswer(route.id, a.id, "slope_size", "bad");

    list.deleteCrux(route.id, a.id);
    expect(cruxesOf(list).map((c) => [c.distance_m, c.deleted])).toEqual([
      [100, true],
      [200, undefined],
    ]);

    list.undeleteCrux(route.id, a.id);
    expect(cruxesOf(list)[0].deleted).toBeUndefined();
    expect(cruxesOf(list)[0].answers).toEqual({ slope_size: "bad" });

    list.updateLine(route.id, [
      [7.8, 62.6],
      [7.82, 62.6],
    ]);
    expect(cruxesOf(list)).toEqual([]);
  });
});
