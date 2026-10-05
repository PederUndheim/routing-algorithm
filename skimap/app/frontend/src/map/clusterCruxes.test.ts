import { describe, expect, it } from "vitest";

import type { Crux } from "../types";
import { clusterCruxes, clusterLabel } from "./clusterCruxes";

/** A Crux at `x` pixels along a horizontal line, with whatever marks the
 *  test is about. Only `number`, `class` and the marks matter here - the
 *  position is supplied by the fake `project` below. */
const crux = (number: number, extra: Partial<Crux> = {}): Crux => ({
  number,
  class: "steep_slope",
  position: { lat: 61, lng: 7 },
  distance_m: number * 100,
  length_m: 50,
  max_slope_deg: 35,
  ...extra,
});

/** Pixel positions keyed by Crux number, so a test says where each sits. */
const at = (xs: Record<number, number>) => (c: Crux) => ({ x: xs[c.number], y: 0 });

/** Every pill 40 wide and 20 high, so the arithmetic in a test is obvious:
 *  a pill at x covers x-10 to x+30. */
const fixed = () => [40, 20] as const;

describe("clustering Cruxes", () => {
  it("leaves markers that do not touch alone", () => {
    const cruxes = [crux(1), crux(2), crux(3)];
    const clusters = clusterCruxes(cruxes, at({ 1: 0, 2: 100, 3: 200 }), fixed);

    expect(clusters.map((c) => c.members.length)).toEqual([1, 1, 1]);
    expect(clusters.map(clusterLabel)).toEqual(["1", "2", "3"]);
  });

  it("merges markers whose pills overlap", () => {
    const cruxes = [crux(1), crux(2), crux(3)];
    const clusters = clusterCruxes(cruxes, at({ 1: 0, 2: 10, 3: 20 }), fixed);

    expect(clusters).toHaveLength(1);
    expect(clusterLabel(clusters[0])).toBe("1-3");
  });

  it("draws a cluster where the route reaches it, not at its middle", () => {
    const cruxes = [crux(7), crux(8)];
    const clusters = clusterCruxes(cruxes, at({ 7: 0, 8: 10 }), fixed);

    expect(clusters[0].head.number).toBe(7);
  });

  it("starts a new cluster where the touching stops", () => {
    const cruxes = [crux(1), crux(2), crux(3), crux(4)];
    // 1 and 2 touch, 3 is far from both, 4 touches 3.
    const clusters = clusterCruxes(cruxes, at({ 1: 0, 2: 10, 3: 300, 4: 310 }), fixed);

    expect(clusters.map(clusterLabel)).toEqual(["1-2", "3-4"]);
  });

  it("keeps growing a cluster against everything already in it", () => {
    // Each pill only touches the one before it. Growing against the whole
    // box means the chain stays one cluster rather than splitting in two.
    const cruxes = [crux(1), crux(2), crux(3), crux(4)];
    const clusters = clusterCruxes(cruxes, at({ 1: 0, 2: 35, 3: 70, 4: 105 }), fixed);

    expect(clusters.map(clusterLabel)).toEqual(["1-4"]);
  });

  it("splits when the markers separate at a closer zoom", () => {
    const cruxes = [crux(1), crux(2)];
    const near = clusterCruxes(cruxes, at({ 1: 0, 2: 10 }), fixed);
    const far = clusterCruxes(cruxes, at({ 1: 0, 2: 400 }), fixed);

    expect(near).toHaveLength(1);
    expect(far).toHaveLength(2);
  });

  it("is drawn as the worst thing in it", () => {
    const cruxes = [
      crux(1, { class: "runout_area", max_slope_deg: undefined }),
      crux(2, { probable_release_area: true }),
      crux(3),
    ];
    const clusters = clusterCruxes(cruxes, at({ 1: 0, 2: 10, 3: 20 }), fixed);

    expect(clusters[0].worst.number).toBe(2);
  });

  it("prefers the steeper where two are equally bad", () => {
    const cruxes = [crux(1, { max_slope_deg: 31 }), crux(2, { max_slope_deg: 44 })];
    const clusters = clusterCruxes(cruxes, at({ 1: 0, 2: 10 }), fixed);

    expect(clusters[0].worst.number).toBe(2);
  });

  it("counts a fall hazard as bad as a release area", () => {
    const cruxes = [crux(1, { fall_hazard: true, max_slope_deg: 52 }), crux(2)];
    const clusters = clusterCruxes(cruxes, at({ 1: 0, 2: 10 }), fixed);

    expect(clusters[0].worst.number).toBe(1);
  });

  it("loses no Crux, however tightly they are packed", () => {
    const cruxes = Array.from({ length: 30 }, (_, i) => crux(i + 1));
    const xs = Object.fromEntries(cruxes.map((c, i) => [c.number, i]));
    const clusters = clusterCruxes(cruxes, at(xs), fixed);

    const inside = clusters.flatMap((c) => c.members.map((m) => m.number));
    expect(inside).toEqual(cruxes.map((c) => c.number));
  });

  it("has nothing to do with an empty route", () => {
    expect(clusterCruxes([], at({}), fixed)).toEqual([]);
  });

  it("clusters by what is drawn, so a wider pill merges sooner", () => {
    const cruxes = [crux(1), crux(2)];
    const positions = at({ 1: 0, 2: 60 });
    const narrow = clusterCruxes(cruxes, positions, () => [40, 20] as const);
    const wide = clusterCruxes(cruxes, positions, () => [90, 20] as const);

    expect(narrow).toHaveLength(2);
    expect(wide).toHaveLength(1);
  });
});
