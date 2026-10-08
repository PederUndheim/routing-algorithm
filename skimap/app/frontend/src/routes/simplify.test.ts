import { describe, expect, it } from "vitest";
import type { Position } from "geojson";

import { simplifyForEditing, simplifyLine } from "./simplify";

// About 1 m of latitude, in degrees.
const M = 1 / 111_195;

describe("simplifying a line", () => {
  it("drops points that lie within the tolerance, keeping the ends and the corners", () => {
    const line: Position[] = [
      [7.8, 62.6],
      [7.8, 62.6 + 100 * M],
      [7.8 + 0.000005, 62.6 + 200 * M], // ~0.26 m off the straight line
      [7.8, 62.6 + 300 * M],
      [7.81, 62.6 + 300 * M], // a real corner
    ];
    expect(simplifyLine(line, 2)).toEqual([line[0], line[3], line[4]]);
  });

  it("leaves a short line exactly as it is", () => {
    const line: Position[] = [
      [7.8, 62.6],
      [7.81, 62.61],
      [7.82, 62.6],
    ];
    expect(simplifyForEditing(line)).toEqual(line);
  });

  it("brings a dense recorded track down to an editable number of points", () => {
    // A wiggly track of 5000 points.
    const track: Position[] = Array.from({ length: 5000 }, (_, i) => [
      7.8 + i * 0.00001,
      62.6 + Math.sin(i / 40) * 0.001,
    ]);
    const edited = simplifyForEditing(track, 150);
    expect(edited.length).toBeLessThanOrEqual(150);
    expect(edited[0]).toEqual(track[0]);
    expect(edited[edited.length - 1]).toEqual(track[track.length - 1]);
  });
});
