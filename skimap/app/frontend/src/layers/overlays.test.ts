import { describe, expect, it } from "vitest";

import { DEFAULT_OVERLAYS, toggleOverlay } from "./overlays";

describe("toggleOverlay", () => {
  it("switches off the other layer of the group", () => {
    const next = toggleOverlay(DEFAULT_OVERLAYS, "slope_runout");
    expect(next.slope_runout).toBe(true);
    expect(next.slope).toBe(false);
  });

  it("does the same for the corridor layers", () => {
    const corridors = toggleOverlay(DEFAULT_OVERLAYS, "colored_corridors");
    const hazard = toggleOverlay(corridors, "hazard_zone_corridors");
    expect(hazard.hazard_zone_corridors).toBe(true);
    expect(hazard.colored_corridors).toBe(false);
  });

  it("leaves the other group alone", () => {
    const next = toggleOverlay(DEFAULT_OVERLAYS, "colored_corridors");
    expect(next.slope).toBe(true);
    expect(toggleOverlay(next, "slope_runout").colored_corridors).toBe(true);
  });

  it("can switch a group off altogether", () => {
    const next = toggleOverlay(DEFAULT_OVERLAYS, "slope");
    expect(next.slope).toBe(false);
    expect(next.slope_runout).toBe(false);
  });

  it("does not switch the other layer back on when one goes off", () => {
    const runout = toggleOverlay(DEFAULT_OVERLAYS, "slope_runout");
    const off = toggleOverlay(runout, "slope_runout");
    expect(off.slope_runout).toBe(false);
    expect(off.slope).toBe(false);
  });
});
