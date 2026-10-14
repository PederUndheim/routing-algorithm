import { describe, expect, it } from "vitest";

import { corridorImage, hasWidths } from "./corridorWidths";
import type { Corridor } from "./types";

const bounds = { west: 1, south: 2, east: 3, north: 4 };
const standard = { png_path: "/corridor/aaaaaaaaaaaa.png", bounds };
const narrow = { png_path: "/corridor/bbbbbbbbbbbb.png", bounds };
const wide = { png_path: "/corridor/cccccccccccc.png", bounds };

describe("corridorImage", () => {
  const corridor: Corridor = { ...standard, widths: { narrow, wide } };

  it("draws the band asked for", () => {
    expect(corridorImage(corridor, "narrow")).toEqual(narrow);
    expect(corridorImage(corridor, "wide")).toEqual(wide);
  });

  it("draws the standard band for standard, without its widths", () => {
    expect(corridorImage(corridor, "standard")).toEqual(standard);
  });

  it("falls back to the standard band where a corridor has no widths", () => {
    expect(corridorImage(standard, "wide")).toEqual(standard);
    expect(hasWidths(standard)).toBe(false);
    expect(hasWidths(corridor)).toBe(true);
  });
});
