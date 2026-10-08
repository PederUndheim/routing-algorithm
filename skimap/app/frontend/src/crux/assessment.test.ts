import { describe, expect, it } from "vitest";

import {
  RATINGS,
  defaultsAt,
  problemHazards,
  problemOf,
  verdictOf,
  hasOwnOverall,
  isCritical,
  isDecided,
  overallOf,
  questionsFor,
  shelfOf,
} from "./assessment";

describe("the aspects asked about a crux", () => {
  it("are all five for steep ground, and only remote triggering for a runout", () => {
    expect(questionsFor({ class: "steep_slope" })).toHaveLength(5);
    expect(questionsFor({ class: "runout_area" }).map((q) => q.factor)).toEqual([
      "remote_triggering",
    ]);
  });

  it("are rated on five steps, and an overall against you, either step, is critical", () => {
    expect(RATINGS.map((r) => r.id)).toEqual(["very_good", "good", "neutral", "bad", "very_bad"]);
    expect(RATINGS.map((r) => isCritical(r.id))).toEqual([false, false, false, true, true]);
    expect(isCritical(undefined)).toBe(false);
  });
});

describe("a crux's overall rating", () => {
  it("is the user's own for steep ground, and the one rating a runout has", () => {
    const answers = { remote_triggering: "bad", slope_size: "very_good" } as const;
    expect(hasOwnOverall({ class: "steep_slope" })).toBe(true);
    expect(overallOf({ class: "steep_slope", answers, overall: "good" })).toBe("good");
    expect(hasOwnOverall({ class: "runout_area" })).toBe(false);
    expect(overallOf({ class: "runout_area", answers, overall: "good" })).toBe("bad");
  });

  it("counts as evaluated only once the crux is kept", () => {
    expect(isDecided({})).toBe(false);
    expect(isDecided({ keep: false })).toBe(false);
    expect(isDecided({ keep: true })).toBe(true);
  });
});

describe("a crux's verdict on the map and in the list", () => {
  const steep = { class: "steep_slope" as const, answers: {} };

  it("shows only once kept: the overall rating, or plain kept without one", () => {
    expect(verdictOf({ ...steep, overall: "bad" })).toBeNull();
    expect(verdictOf({ ...steep, overall: "bad", keep: true })).toBe("bad");
    expect(verdictOf({ ...steep, keep: true })).toBe("kept");
    expect(
      verdictOf({ class: "runout_area", answers: { remote_triggering: "good" }, keep: true })
    ).toBe("good");
  });

  it("reads a crux's symbol back from its marks", () => {
    expect(problemOf({ class: "runout_area" })).toBe("runout_area");
    expect(problemOf({ class: "steep_slope", fall_hazard: true })).toBe("fall_hazard");
    expect(problemOf({ class: "steep_slope", probable_release_area: true, fall_hazard: true })).toBe(
      "release_area"
    );
    expect(problemOf({ class: "steep_slope" })).toBe("steep_slope");
  });
});

describe("a snow conditions check", () => {
  it("has no aspects to rate, only an overall rating of its own", () => {
    const check = { ...problemHazards("snow_check"), answers: {}, overall: "bad" as const };
    expect(questionsFor(check)).toEqual([]);
    expect(hasOwnOverall(check)).toBe(true);
    expect(overallOf(check)).toBe("bad");
    expect(problemOf(check)).toBe("snow_check");
  });
});

describe("where a crux is listed", () => {
  it("is active until the user decides otherwise, whatever its rating", () => {
    expect(shelfOf({})).toBe("active");
    expect(shelfOf({ keep: true })).toBe("active");
  });

  it("goes to the not-kept shelf when the user removes it from the list", () => {
    expect(shelfOf({ keep: false })).toBe("not_kept");
  });

  it("goes to the deleted shelf when deleted, whatever was decided", () => {
    expect(shelfOf({ deleted: true })).toBe("deleted");
    expect(shelfOf({ keep: false, deleted: true })).toBe("deleted");
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
    expect(defaultsAt(segments, 150)).toEqual({ problem: "fall_hazard" });
    expect(defaultsAt(segments, 250)).toEqual({ problem: "runout_area" });
  });

  it("are plain steep ground where nothing is known, so all five are asked", () => {
    expect(defaultsAt(segments, 50)).toEqual({ problem: "steep_slope" });
    expect(defaultsAt(segments, 350)).toEqual({ problem: "steep_slope" });
    expect(defaultsAt(undefined, 50)).toEqual({ problem: "steep_slope" });
  });
});
