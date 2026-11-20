import { describe, expect, it } from "vitest";
import {
  agreedStep, byDoubt, disagreements, doubtOf, hintLabel, hintSize, majorityNeighbour, sizeHint, statusOf, viewOf,
  type ExpertVerdicts,
} from "./agreement";
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

describe("auto-klassifisert", () => {
  it("takes one main class whatever the −/0/+, size and notes", () => {
    const verdicts = three({ sub: -1, note: "fin", size: 1 }, { sub: 1 });
    expect(agreedStep(experts, verdicts, 7)).toEqual({ kast: "blue", sub: 0 });
    expect(disagreements(experts, verdicts, 7)).toEqual([]);
  });

  it("takes majority + neighbour, at the median of the twelve steps", () => {
    // blå 0, blå +, rød −: steps 4, 5, 6 -> blå +
    expect(agreedStep(experts, three({}, { sub: 1 }, { kast: "red", sub: -1 }), 7)).toEqual({ kast: "blue", sub: 1 });
    // blå −, blå −, grønn +: steps 3, 3, 2 -> blå −
    expect(agreedStep(experts, three({ sub: -1 }, { sub: -1 }, { kast: "green", sub: 1 }), 7))
      .toEqual({ kast: "blue", sub: -1 });
    // rød +, svart −, svart 0 -> svart −
    expect(agreedStep(experts, three({ kast: "red", sub: 1 }, { kast: "black", sub: -1 }, { kast: "black" }), 7))
      .toEqual({ kast: "black", sub: -1 });
  });

  it("sends a class two apart, or three different, to the meeting", () => {
    expect(agreedStep(experts, three({}, {}, { kast: "black" }), 7)).toBeNull();
    expect(agreedStep(experts, three({ kast: "green" }, {}, { kast: "red" }), 7)).toBeNull();
    expect(majorityNeighbour(["blue", "blue", "red"])).toBe(true);
    expect(majorityNeighbour(["green", "blue", "red"])).toBe(false);
  });

  it("sends Problematisk always, Usikker only when the classes differ and it is in the majority", () => {
    expect(agreedStep(experts, three({}, {}, { problematic: true }), 7)).toBeNull();
    expect(agreedStep(experts, three({ doubt: true }), 7)).toEqual({ kast: "blue", sub: 0 });
    // one of the two blue unsure: to the meeting
    expect(agreedStep(experts, three({ doubt: true }, {}, { kast: "red" }), 7)).toBeNull();
    // only the lone red one unsure: the majority holds, median as usual
    expect(agreedStep(experts, three({}, { sub: 1 }, { kast: "red", sub: -1, doubt: true }), 7))
      .toEqual({ kast: "blue", sub: 1 });
    // the lone one and one of the majority: to the meeting
    expect(agreedStep(experts, three({ doubt: true }, {}, { kast: "red", doubt: true }), 7)).toBeNull();
    expect(doubtOf(experts, three({}, {}, { kast: "red", doubt: true }), 7).lone).toBe(true);
    expect(doubtOf(experts, three({ doubt: true }), 7).lone).toBe(false);
  });

  it("waits for every expert", () => {
    const verdicts = three({});
    delete verdicts.andreas[7];
    expect(agreedStep(experts, verdicts, 7)).toBeNull();
    expect(disagreements(experts, verdicts, 7)).toEqual(["Ikke vurdert av Andreas"]);
    expect(agreedStep(experts, three({}, { kast: null }), 7)).toBeNull();
  });

  it("names why it goes to the meeting", () => {
    expect(disagreements(experts, three({ doubt: true }, { kast: "black", problematic: true }), 7)).toEqual([
      "For ulike klasser (blå, svart)", "Problematisk: Finn", "Usikker og ulik klasse: Håvard",
    ]);
  });
});

describe("view and status", () => {
  it("shows the experts' class until the meeting sets one", () => {
    const green = { kast: "green" as const, sub: 1 as const };
    expect(viewOf(undefined, green)).toEqual({ consensus: { ...EMPTY_CONSENSUS, kast: "green", sub: 1 }, auto: true });
    const set = { ...EMPTY_CONSENSUS, kast: "red" as const };
    expect(viewOf(set, green)).toEqual({ consensus: set, auto: false });
    expect(viewOf(undefined, null)).toEqual({ consensus: EMPTY_CONSENSUS, auto: false });
  });

  it("counts agreed corridors as agreed even once changed", () => {
    const green = { kast: "green" as const, sub: 0 as const };
    expect(statusOf(undefined, green)).toBe("agreed");
    expect(statusOf({ ...EMPTY_CONSENSUS, kast: "red" }, green)).toBe("agreed");
    expect(statusOf({ ...EMPTY_CONSENSUS, kast: "red" }, null)).toBe("settled");
    expect(statusOf({ ...EMPTY_CONSENSUS, note: "x" }, null)).toBe("todo");
  });
});

describe("review of the auto-classification", () => {
  const blue = { kast: "blue" as const, sub: 0 as const };

  it("takes a reopened corridor back to the meeting, empty", () => {
    const back = { ...EMPTY_CONSENSUS, reopened: true };
    expect(statusOf(back, blue)).toBe("reopened");
    expect(viewOf(back, blue)).toEqual({ consensus: back, auto: false });
    expect(statusOf({ ...back, kast: "red" }, blue)).toBe("settled");
    expect(statusOf({ ...EMPTY_CONSENSUS, reopened: false }, blue)).toBe("agreed");
  });

  it("names who asked for another width", () => {
    expect(sizeHint(experts, three({}), 7)).toBeNull();
    const one = sizeHint(experts, three({}, { size: -1 }), 7)!;
    expect(one).toEqual({ smaller: ["Finn"], bigger: [] });
    expect([hintSize(one), hintLabel(one)]).toEqual([-1, "Mindre"]);
    const both = sizeHint(experts, three({ size: 1 }, { size: -1 }), 7)!;
    expect([hintSize(both), hintLabel(both)]).toEqual([null, "Mindre/Større"]);
  });

  it("puts the most doubtful first", () => {
    const order = [
      three({}, {}, {}),                                   // nothing
      three({ note: "hm" }),                               // a note
      three({ doubt: true }),                              // Usikker
      three({ sub: -1 }, {}, { sub: 1 }),                  // spread 2
      three({ size: 1 }),                                  // a width
      three({ size: 1 }, {}, { sub: 1 }),                  // a width, spread 1
      three({}, {}, { kast: "red", sub: -1 }),             // split, spread 2
      three({ sub: -1 }, {}, { kast: "red", sub: 1 }),     // split, spread 4
      three({ size: -1 }, {}, { kast: "red", sub: -1 }),   // split and a width
    ].map((v) => doubtOf(experts, v, 7));
    const sorted = [...order].sort(byDoubt);
    expect(sorted).toEqual([...order].reverse());
  });
});
