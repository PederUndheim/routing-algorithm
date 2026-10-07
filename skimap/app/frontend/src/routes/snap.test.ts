import { describe, expect, it } from "vitest";

import { nearestOnLine } from "./snap";

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
