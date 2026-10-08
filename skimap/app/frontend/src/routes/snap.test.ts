import { describe, expect, it } from "vitest";

import { geodesicLength } from "./routeList";
import { markerSpot, nearestOnLine, pointAtDistance, sliceLine } from "./snap";

// An L: 0.01 deg east, then 0.01 deg north, at 62.6 N.
const line = {
  type: "LineString" as const,
  coordinates: [
    [7.8, 62.6],
    [7.81, 62.6],
    [7.81, 62.61],
  ],
};

describe("snapping to a route", () => {
  it("drops a point beside the first leg straight onto it, measured from the start", () => {
    const { position, distance_m } = nearestOnLine(line, { lat: 62.601, lng: 7.805 });
    expect(position.lat).toBeCloseTo(62.6, 6);
    expect(position.lng).toBeCloseTo(7.805, 6);
    // Half of a ~512 m leg.
    expect(distance_m).toBeGreaterThan(250);
    expect(distance_m).toBeLessThan(262);
  });

  it("picks the nearer leg, and counts the whole first leg before it", () => {
    const { position, distance_m } = nearestOnLine(line, { lat: 62.605, lng: 7.812 });
    expect(position.lng).toBeCloseTo(7.81, 6);
    expect(position.lat).toBeCloseTo(62.605, 6);
    // The first leg, then half of the ~1112 m second one.
    expect(distance_m).toBeGreaterThan(512 + 550);
    expect(distance_m).toBeLessThan(512 + 565);
  });

  it("clamps to the end when the point lies beyond it", () => {
    const { position } = nearestOnLine(line, { lat: 62.7, lng: 7.81 });
    expect(position.lat).toBeCloseTo(62.61, 9);
    expect(position.lng).toBeCloseTo(7.81, 9);
  });
});

describe("a Crux's marker", () => {
  it("is found by walking a distance along the line, round the corner too", () => {
    expect(pointAtDistance(line, 0)).toEqual({ lat: 62.6, lng: 7.8 });
    const around = pointAtDistance(line, 512 + 556);
    expect(around.lng).toBeCloseTo(7.81, 6);
    expect(around.lat).toBeCloseTo(62.605, 3);
  });

  it("clamps to the ends of the line", () => {
    expect(pointAtDistance(line, -10)).toEqual({ lat: 62.6, lng: 7.8 });
    expect(pointAtDistance(line, 1e6)).toEqual({ lat: 62.61, lng: 7.81 });
  });

  it("sits 30 m before the Crux along the line", () => {
    const crux = { lat: 62.605, lng: 7.81 };
    const spot = markerSpot(line, crux);
    const before = nearestOnLine(line, spot).distance_m;
    const at = nearestOnLine(line, crux).distance_m;
    expect(at - before).toBeCloseTo(30, 0);
    expect(geodesicLength([[spot.lng, spot.lat], [crux.lng, crux.lat]])).toBeCloseTo(30, 0);
  });

  it("stays at the start of the line for a Crux nearer to it than 30 m", () => {
    expect(markerSpot(line, { lat: 62.6, lng: 7.8003 })).toEqual({ lat: 62.6, lng: 7.8 });
  });
});

describe("slicing a route", () => {
  it("cuts between two distances, keeping the corner that lies between them", () => {
    const slice = sliceLine(line, 412, 512 + 556);
    expect(slice[0][0]).toBeCloseTo(7.808, 3);
    expect(slice[1]).toEqual([7.81, 62.6]);
    expect(slice[2][1]).toBeCloseTo(62.605, 3);
    expect(slice).toHaveLength(3);
  });

  it("clamps to the ends, and is empty when nothing lies between", () => {
    expect(sliceLine(line, -100, 1e6)).toEqual(line.coordinates);
    expect(sliceLine(line, 300, 300)).toEqual([]);
    expect(sliceLine(line, 1e6, 2e6)).toEqual([]);
  });
});
