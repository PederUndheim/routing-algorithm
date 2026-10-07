import { describe, expect, it } from "vitest";

import { assess, categoryOfCrux, categoryOfSlope, defaultsAt, questionsFor } from "./assessment";
import type { Answers } from "../types";

const allNo: Answers = {
  slope_size: false,
  release_volume: false,
  terrain_traps: false,
  safe_spots: false,
  remote_triggering: false,
};

describe("slope categories", () => {
  it("split at 30, 35 and 40 degrees", () => {
    expect([29.9, 30, 34.9, 35, 39.9, 40].map(categoryOfSlope)).toEqual([
      "lt30",
      "30_34",
      "30_34",
      "35_39",
      "35_39",
      "gt39",
    ]);
  });

  it("put a Runout area under 30, and a Steep slope by its steepest ground", () => {
    expect(categoryOfCrux({ class: "runout_area" })).toBe("lt30");
    expect(categoryOfCrux({ class: "steep_slope", max_slope_deg: 37 })).toBe("35_39");
    expect(categoryOfCrux({ class: "steep_slope" })).toBe("30_34");
  });
});

describe("assessing a crux", () => {
  it("under 30 asks only about remote triggering: yes keeps it, no dismisses it", () => {
    expect(questionsFor("lt30").map((q) => q.factor)).toEqual(["remote_triggering"]);
    expect(assess("lt30", {})).toBe("unassessed");
    expect(assess("lt30", { remote_triggering: true })).toBe("kept");
    expect(assess("lt30", { remote_triggering: false })).toBe("dismissed");
  });

  it("in 30-34 is critical from two yes, kept below that once all are answered", () => {
    expect(assess("30_34", { slope_size: true })).toBe("unassessed");
    expect(assess("30_34", { slope_size: true, safe_spots: true })).toBe("critical");
    expect(assess("30_34", { ...allNo, terrain_traps: true })).toBe("kept");
  });

  it("in 35-39 is critical from one yes, kept when all are no", () => {
    expect(assess("35_39", { release_volume: true })).toBe("critical");
    expect(assess("35_39", { slope_size: false })).toBe("unassessed");
    expect(assess("35_39", allNo)).toBe("kept");
  });

  it("over 39 is always critical, whatever is answered", () => {
    expect(assess("gt39", {})).toBe("critical");
    expect(assess("gt39", allNo)).toBe("critical");
  });
});

describe("defaults for a crux placed by hand", () => {
  const line = { type: "LineString" as const, coordinates: [] };
  const segments = [
    { class: "none" as const, start_m: 0, end_m: 100, line },
    { class: "steep_slope" as const, max_slope_deg: 36, fall_hazard: true, start_m: 100, end_m: 200, line },
    { class: "runout_area" as const, start_m: 200, end_m: 300, line },
    { class: "no_data" as const, start_m: 300, end_m: 400, line },
  ];

  it("come from the analysed stretch the point falls on", () => {
    expect(defaultsAt(segments, 150)).toEqual({ category: "35_39", problem: "fall_hazard" });
    expect(defaultsAt(segments, 250)).toEqual({ category: "lt30", problem: "runout_area" });
    expect(defaultsAt(segments, 50)).toEqual({ category: "lt30", problem: "steep_slope" });
  });

  it("leave the category to the user where nothing is known", () => {
    expect(defaultsAt(segments, 350).category).toBeNull();
    expect(defaultsAt(undefined, 50).category).toBeNull();
  });
});
