// @vitest-environment jsdom
import type { LineString, Position } from "geojson";
import { describe, expect, it } from "vitest";

import type { GroundSummary, ImproveResponse, Suggestion } from "../types";
import { createRouteList, geodesicLength } from "./routeList";
import { locateNear, placeSuggestions, relocate, spliceSuggestion, verdictOf } from "./suggestions";

const LAT = 62.6;

/** East along one latitude, a point every 0.002 degrees (about 100 m). */
const straight = (from = 7.8, to = 7.84): LineString => {
  const coordinates: Position[] = [];
  for (let lng = from; lng <= to + 1e-9; lng += 0.002) coordinates.push([lng, LAT]);
  return { type: "LineString", coordinates };
};

const ground = (over: Partial<GroundSummary> = {}): GroundSummary => ({
  length_m: 100,
  steep_m: 0,
  release_m: 0,
  fall_m: 0,
  runout_m: 0,
  no_data_m: 0,
  ...over,
});

const along = (line: LineString, lng: number) => geodesicLength([line.coordinates[0], [lng, LAT]]);

/** A way off the line between two longitudes, out to the north and back. */
const bump = (line: LineString, from: number, to: number): Suggestion => ({
  start_m: along(line, from),
  end_m: along(line, to),
  line: {
    type: "LineString",
    coordinates: [
      [from, LAT],
      [(from + to) / 2, LAT + 0.0005],
      [to, LAT],
    ],
  },
  cost: 50,
  old_cost: 100,
  before: ground({ steep_m: 100 }),
  after: ground(),
});

const response = (line: LineString, ...suggestions: Suggestion[]): ImproveResponse => ({
  suggestions,
  length_m: geodesicLength(line.coordinates),
  seconds: 1,
});

let id = 0;
const nextId = () => `s${++id}`;

describe("placeSuggestions", () => {
  it("finds where each leaves and rejoins the line", () => {
    const line = straight();
    const [placed] = placeSuggestions(line, response(line, bump(line, 7.81, 7.82)), nextId);
    expect(placed.startM).toBeCloseTo(along(line, 7.81), 1);
    expect(placed.endM).toBeCloseTo(along(line, 7.82), 1);
  });

  it("scales the backend's measure before looking", () => {
    const line = straight();
    const s = bump(line, 7.81, 7.82);
    // The grid measured the line 2% longer; the ends are still found.
    const grid = { ...response(line, { ...s, start_m: s.start_m * 1.02, end_m: s.end_m * 1.02 }) };
    grid.length_m *= 1.02;
    const [placed] = placeSuggestions(line, grid, nextId);
    expect(placed.startM).toBeCloseTo(along(line, 7.81), 1);
  });
});

describe("locateNear", () => {
  it("finds the pass it was told to look near, not the nearest overall", () => {
    // Out east and back west 5 m north: the same ground twice.
    const out = straight();
    const back = [...out.coordinates].reverse().map(([lng]) => [lng, LAT + 0.000045]);
    const line: LineString = { type: "LineString", coordinates: [...out.coordinates, ...back] };
    const there = along(out, 7.82);
    const total = geodesicLength(line.coordinates);
    const onTheWayBack = total - there;
    expect(locateNear(line, [7.82, LAT], there)).toBeCloseTo(there, 0);
    expect(locateNear(line, [7.82, LAT], onTheWayBack)).toBeGreaterThan(total / 2);
  });
});

describe("spliceSuggestion", () => {
  it("keeps every point either side and puts the way between", () => {
    const line = straight();
    const [s] = placeSuggestions(line, response(line, bump(line, 7.81, 7.82)), nextId);
    const spliced = spliceSuggestion(line, s);

    const before = line.coordinates.filter(([lng]) => lng < 7.81 - 1e-9);
    const after = line.coordinates.filter(([lng]) => lng > 7.82 + 1e-9);
    expect(spliced.slice(0, before.length)).toEqual(before);
    expect(spliced.slice(spliced.length - after.length)).toEqual(after);
    expect(spliced).toContainEqual(s.line.coordinates[1]);
    // No point twice where the way meets the line.
    const lngs = spliced.map(([lng]) => lng);
    expect(new Set(lngs.map((l) => l.toFixed(9))).size).toBe(lngs.length);
  });

  it("works from the very start of the line", () => {
    const line = straight();
    const [s] = placeSuggestions(line, response(line, bump(line, 7.8, 7.81)), nextId);
    const spliced = spliceSuggestion(line, s);
    expect(spliced[0]).toEqual([7.8, LAT]);
    expect(spliced[1]).toEqual(s.line.coordinates[1]);
  });
});

describe("relocate", () => {
  it("moves the ones after a taken suggestion along by what it added", () => {
    const line = straight();
    const [first, second] = placeSuggestions(
      line,
      response(line, bump(line, 7.81, 7.82), bump(line, 7.83, 7.835)),
      nextId
    );
    const next: LineString = { type: "LineString", coordinates: spliceSuggestion(line, first) };
    const [moved] = relocate([second], first, line, next);
    const added = geodesicLength(next.coordinates) - geodesicLength(line.coordinates);
    expect(added).toBeGreaterThan(1);
    expect(moved.startM).toBeCloseTo(second.startM + added, 0);
    expect(moved.endM).toBeCloseTo(second.endM + added, 0);
  });
});

describe("verdictOf", () => {
  const s = (before: Partial<GroundSummary>, after: Partial<GroundSummary>) => ({
    ...bump(straight(), 7.81, 7.82),
    before: ground(before),
    after: ground(after),
  });

  it("is safer off steep ground, riskier onto it, easier otherwise", () => {
    expect(verdictOf(s({ steep_m: 100 }, { steep_m: 20 }))).toBe("safer");
    expect(verdictOf(s({ steep_m: 0 }, { steep_m: 40 }))).toBe("riskier");
    expect(verdictOf(s({ runout_m: 200 }, { runout_m: 0 }))).toBe("easier");
  });

  it("counts a release slope swapped for a plain steep one as safer", () => {
    expect(verdictOf(s({ steep_m: 60, release_m: 60 }, { steep_m: 60 }))).toBe("safer");
  });
});

describe("a Route's suggestions", () => {
  const drawnWithSuggestions = () => {
    const list = createRouteList();
    const line = straight();
    const route = list.addDrawn(line.coordinates);
    list.attachSuggestions(
      route.id,
      route.line,
      response(line, bump(line, 7.81, 7.82), bump(line, 7.83, 7.835))
    );
    return { list, route: () => list.getState().routes[0] };
  };

  it("accepting one puts its way in the line and keeps the other, found again", () => {
    const { list, route } = drawnWithSuggestions();
    const [first, second] = route().suggestions!;
    list.acceptSuggestion(route().id, first.id);

    expect(route().line.coordinates).toContainEqual(first.line.coordinates[1]);
    expect(route().suggestions!.map((s) => s.id)).toEqual([second.id]);
    expect(route().suggestions![0].startM).toBeGreaterThan(second.startM);
  });

  it("rejecting one leaves the line alone", () => {
    const { list, route } = drawnWithSuggestions();
    const line = route().line;
    list.rejectSuggestion(route().id, route().suggestions![0].id);
    expect(route().line).toBe(line);
    expect(route().suggestions).toHaveLength(1);
  });

  it("an edit drops them, and ones found for the old line are not taken", () => {
    const { list, route } = drawnWithSuggestions();
    const old = route().line;
    list.updateLine(route().id, straight(7.8, 7.83).coordinates);
    expect(route().suggestions).toBeUndefined();

    list.attachSuggestions(route().id, old, response(old, bump(old, 7.81, 7.82)));
    expect(route().suggestions).toBeUndefined();
  });

  it("dismissing them goes back to not having looked", () => {
    const { list, route } = drawnWithSuggestions();
    list.dismissSuggestions(route().id);
    expect(route().suggestions).toBeUndefined();
  });
});
