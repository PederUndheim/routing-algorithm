import { describe, expect, it } from "vitest";

import type { LatLng, Waypoints } from "../types";
import {
  NO_WAYPOINTS,
  insertPoint,
  pick,
  pointLabel,
  removePoint,
  setNetwork,
} from "./waypoints";

const p = (n: number): LatLng => ({ lat: 60 + n / 100, lng: 8 });

const three: Waypoints = { points: [p(0), p(1), p(2)], networks: ["road", "terrain"] };

describe("pick points", () => {
  it("takes the start, then the end, then stops", () => {
    const first = pick(NO_WAYPOINTS, { kind: "sequence" }, p(0));
    expect(first.waypoints.points).toEqual([p(0)]);
    expect(first.mode).toEqual({ kind: "sequence" });

    const second = pick(first.waypoints, first.mode!, p(1));
    expect(second.waypoints).toEqual({ points: [p(0), p(1)], networks: ["terrain"] });
    expect(second.mode).toBeNull();
  });

  it("moves one point and leaves the legs alone", () => {
    const { waypoints, mode } = pick(three, { kind: "replace", index: 1 }, p(9));
    expect(waypoints).toEqual({ points: [p(0), p(9), p(2)], networks: ["road", "terrain"] });
    expect(mode).toBeNull();
  });
});

describe("inserting a point", () => {
  it("after the end makes a new leg over the terrain", () => {
    const roads = setNetwork(three, 1, "road");
    expect(insertPoint(roads, 3, p(3)).networks).toEqual(["road", "road", "terrain"]);
  });

  it("into a leg splits it, both halves going as it did", () => {
    const w = insertPoint(three, 1, p(5));
    expect(w.points).toEqual([p(0), p(5), p(1), p(2)]);
    expect(w.networks).toEqual(["road", "road", "terrain"]);
  });
});

describe("removing a point", () => {
  it("takes the start's leg with it", () => {
    expect(removePoint(three, 0)).toEqual({ points: [p(1), p(2)], networks: ["terrain"] });
  });

  it("takes the end's leg with it", () => {
    expect(removePoint(three, 2)).toEqual({ points: [p(0), p(1)], networks: ["road"] });
  });

  it("joins a waypoint's two legs, going as the first did", () => {
    expect(removePoint(three, 1)).toEqual({ points: [p(0), p(2)], networks: ["road"] });
  });

  it("leaves no legs with one point left", () => {
    expect(removePoint(removePoint(three, 0), 0)).toEqual({ points: [p(2)], networks: [] });
  });
});

describe("labels", () => {
  it("names the ends and numbers the waypoints between", () => {
    expect([0, 1, 2, 3].map((i) => pointLabel(i, 4))).toEqual([
      "Start",
      "Waypoint 1",
      "Waypoint 2",
      "End",
    ]);
    expect(pointLabel(0, 1)).toBe("Start");
  });
});
