import { describe, expect, it } from "vitest";
import { agreedClass, disagreements, statusOf, viewOf, type ExpertVerdicts } from "./agreement";
import { EMPTY_CONSENSUS, type Expert, type Verdict } from "./types";

const experts: Expert[] = [
  { id: "havard", name: "Håvard" }, { id: "finn", name: "Finn" }, { id: "andreas", name: "Andreas" },
];
const v = (patch: Partial<Verdict> = {}): Verdict => ({
  kast: "blue", sub: 0, size: 0, note: "", doubt: false, problematic: false, ...patch,
});
const three = (a: Partial<Verdict>, b: Partial<Verdict> = {}, c: Partial<Verdict> = {}): ExpertVerdicts => ({
  havard: { 7: v(a) }, finn: { 7: v(b) }, andreas: { 7: v(c) },
});

describe("agreement", () => {
  it("agrees on the main class whatever the −/0/+ and notes", () => {
    const verdicts = three({ sub: -1, note: "fin" }, { sub: 1 });
    expect(agreedClass(experts, verdicts, 7)).toBe("blue");
    expect(disagreements(experts, verdicts, 7)).toEqual([]);
  });

  it("does not agree on a different class, size, flag or doubt", () => {
    expect(agreedClass(experts, three({}, { kast: "red" }), 7)).toBeNull();
    expect(agreedClass(experts, three({}, { size: 1 }), 7)).toBeNull();
    expect(agreedClass(experts, three({}, {}, { problematic: true }), 7)).toBeNull();
    expect(agreedClass(experts, three({ doubt: true }), 7)).toBeNull();
  });

  it("does not agree when an expert has not judged it", () => {
    const verdicts = three({});
    delete verdicts.andreas[7];
    expect(agreedClass(experts, verdicts, 7)).toBeNull();
    expect(disagreements(experts, verdicts, 7)).toEqual(["Ikke vurdert av Andreas"]);
    expect(agreedClass(experts, three({}, { kast: null }), 7)).toBeNull();
  });

  it("names who differs", () => {
    expect(disagreements(experts, three({ size: -1 }, { kast: "red", problematic: true }), 7)).toEqual([
      "Ulik klasse (blå, rød)", "Størrelse: Håvard", "Problematisk: Finn",
    ]);
  });
});

describe("view and status", () => {
  it("shows the experts' class until the meeting sets one", () => {
    expect(viewOf(undefined, "green")).toEqual({ consensus: { ...EMPTY_CONSENSUS, kast: "green" }, auto: true });
    const set = { ...EMPTY_CONSENSUS, kast: "red" as const };
    expect(viewOf(set, "green")).toEqual({ consensus: set, auto: false });
    expect(viewOf(undefined, null)).toEqual({ consensus: EMPTY_CONSENSUS, auto: false });
  });

  it("counts agreed corridors as agreed even once changed", () => {
    expect(statusOf(undefined, "green")).toBe("agreed");
    expect(statusOf({ ...EMPTY_CONSENSUS, kast: "red" }, "green")).toBe("agreed");
    expect(statusOf({ ...EMPTY_CONSENSUS, kast: "red" }, null)).toBe("settled");
    expect(statusOf({ ...EMPTY_CONSENSUS, note: "x" }, null)).toBe("todo");
  });
});
