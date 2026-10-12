import type { LineString, Position } from "geojson";
import { describe, expect, it } from "vitest";

import type { CruxEntry, CruxResult } from "../types";
import { carryOverEdit, mergeIdentified, remapStretch } from "./carryOver";
import { geodesicLength, isEdited } from "./routeList";
import { restoreUnedited } from "./simplify";

// Due east along 62.6 N, a point every 0.002 deg - about 103 m - for ~1 km.
const straight: Position[] = Array.from({ length: 11 }, (_, i) => [7.8 + i * 0.002, 62.6]);
const oldLine: LineString = { type: "LineString", coordinates: straight };
const length = geodesicLength(straight);
const step = length / 10;

// The middle point pulled ~110 m north: the two legs either side of it
// change, the rest of the line is where it was.
const bent: LineString = {
  type: "LineString",
  coordinates: straight.map((p, i) => (i === 5 ? [p[0], p[1] + 0.001] : p)),
};

const crux = (id: string, start_m: number, end_m: number, extra: Partial<CruxEntry> = {}): CruxEntry => ({
  id,
  number: 1,
  class: "steep_slope",
  source: "identified",
  answers: {},
  position: { lat: 62.6, lng: 7.8 + (start_m / length) * 0.02 },
  distance_m: start_m,
  length_m: end_m - start_m,
  area: { start_m, end_m },
  ...extra,
});

describe("a stretch through an edit", () => {
  it("is where it was if the edit left it alone", () => {
    const moved = remapStretch(oldLine, bent, { start_m: 0, end_m: 2 * step });
    expect(moved?.start_m).toBeCloseTo(0, 0);
    expect(moved?.end_m).toBeCloseTo(2 * step, 0);
  });

  it("is gone if any of it was moved", () => {
    expect(remapStretch(oldLine, bent, { start_m: 3 * step, end_m: 4.5 * step })).toBeNull();
  });
});

describe("carrying a Route's analysis over an edit", () => {
  const result: CruxResult = {
    segments: [
      { class: "steep_slope", start_m: 0, end_m: length, line: oldLine },
    ],
    cruxes: [],
    length_m: length,
    no_data_m: 0,
  };

  it("keeps the Cruxes the edit left alone, with what the user made of them", () => {
    const rated = crux("a", 0, 2 * step, { answers: { slope_size: "bad" }, keep: true });
    const { cruxes } = carryOverEdit(oldLine, bent, result, [rated, crux("b", 4.5 * step, 5.5 * step)]);
    expect(cruxes.map((c) => c.id)).toEqual(["a"]);
    expect(cruxes[0].answers).toEqual({ slope_size: "bad" });
    expect(cruxes[0].keep).toBe(true);
  });

  it("keeps one placed by hand on changed ground, snapped onto the new line", () => {
    const manual = crux("m", 5 * step, 5 * step, {
      source: "manual",
      area: undefined,
      position: { lat: 62.6, lng: 7.81 },
    });
    const { cruxes } = carryOverEdit(oldLine, bent, result, [manual]);
    expect(cruxes).toHaveLength(1);
    // On the bent line now: north of where it was.
    expect(cruxes[0].position.lat).toBeGreaterThan(62.6);
  });

  it("keeps the colours on unchanged ground and counts the rest as unanalysed", () => {
    const { crux: kept, unanalysed_m } = carryOverEdit(oldLine, bent, result, []);
    expect(kept?.segments).toHaveLength(2);
    // The two changed legs, each a little longer now they are bent.
    expect(unanalysed_m).toBeGreaterThan(2 * step - 20);
    expect(unanalysed_m).toBeLessThan(2 * step + 120);
  });

  it("changes nothing on a line saved untouched", () => {
    const { crux: kept, cruxes, unanalysed_m } = carryOverEdit(
      oldLine,
      { type: "LineString", coordinates: [...straight] },
      result,
      [crux("a", 0, length)]
    );
    expect(kept?.segments).toHaveLength(1);
    expect(cruxes).toHaveLength(1);
    expect(unanalysed_m).toBeLessThan(1);
  });
});

describe("updating cruxes", () => {
  it("keeps what the user made of a Crux found again", () => {
    const old = crux("old", 100, 300, { answers: { slope_size: "bad" }, overall: "bad" });
    const fresh = crux("new", 110, 310);
    const [merged] = mergeIdentified([old], [fresh], isEdited);
    expect(merged.id).toBe("old");
    expect(merged.answers).toEqual({ slope_size: "bad" });
    expect(merged.area).toEqual({ start_m: 110, end_m: 310 });
  });

  it("takes one found again that nobody touched as found, under its old id", () => {
    const [merged] = mergeIdentified([crux("old", 100, 300)], [crux("new", 110, 310)], isEdited);
    expect(merged.id).toBe("old");
    expect(merged.distance_m).toBe(110);
  });

  it("adds new ones, drops untouched ones not found again, and keeps worked-on ones", () => {
    const merged = mergeIdentified(
      [crux("gone", 0, 50), crux("rated", 500, 600, { keep: false })],
      [crux("new", 800, 900)],
      isEdited
    );
    expect(merged.map((c) => c.id).sort()).toEqual(["new", "rated"]);
  });
});

describe("saving an edited line", () => {
  // A fine line, opened with every other point.
  const fine: Position[] = Array.from({ length: 9 }, (_, i) => [7.8 + i * 0.001, 62.6 + (i % 2) * 0.0001]);
  const opened = fine.filter((_, i) => i % 2 === 0);

  it("puts the detail back where the line was not touched", () => {
    expect(restoreUnedited(fine, opened, opened)).toEqual(fine);
  });

  it("leaves a changed stretch as edited, and the rest as it was", () => {
    const edited = opened.map((p, i) => (i === 2 ? [p[0], p[1] + 0.001] : p));
    const saved = restoreUnedited(fine, opened, edited);
    expect(saved.slice(0, 3)).toEqual(fine.slice(0, 3));
    expect(saved).toContainEqual(edited[2]);
    expect(saved).not.toContainEqual(fine[3]);
    expect(saved.slice(-2)).toEqual(fine.slice(-2));
  });
});
