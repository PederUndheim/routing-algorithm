import {
  EMPTY_CONSENSUS, KAST_LABEL, type Consensus, type CorridorInfo, type Expert,
  type KastClass, type Step, type Verdict,
} from "./types";

/** expert id -> corridor id -> verdict */
export type ExpertVerdicts = Record<string, Record<number, Verdict>>;

const CLASS_ORDER: KastClass[] = ["green", "blue", "red", "black"];

/** 0 (grønn −) .. 11 (svart +): the validation's twelve steps in a row. */
const stepOf = (v: Verdict) => CLASS_ORDER.indexOf(v.kast as KastClass) * 3 + v.sub + 1;

/** All in one main class, or all but one in one class and that one in the
 *  class next to it (any step). With fewer than three, only the first. */
export function majorityNeighbour(classes: KastClass[]): boolean {
  if (new Set(classes).size <= 1) return true;
  if (classes.length < 3) return false;
  const idx = classes.map((k) => CLASS_ORDER.indexOf(k));
  return [...new Set(idx)].some((c) => {
    const others = idx.filter((i) => i !== c);
    return others.length === 1 && Math.abs(others[0] - c) === 1;
  });
}

/** Why the corridor goes to the meeting, one line each; empty when it is
 *  auto-klassifisert (done before the meeting starts). That needs every
 *  expert in the meeting to have set a class, and
 *    - the classes to be majority + neighbour: all the same main class, or
 *      two in one and the third in the class next to it,
 *    - nobody to have ticked Problematisk,
 *    - nobody to have ticked Usikker - unless all gave the same main class.
 *  Corridor size and notes do not count; they are shown, but do not stop it.
 *  The rule is "majority" + "split" in corridor_validation/consensus_rules.py. */
export function disagreements(experts: Expert[], verdicts: ExpertVerdicts, id: number): string[] {
  const reasons: string[] = [];
  const given = experts.map((e) => ({ e, v: verdicts[e.id]?.[id] }));
  const missing = given.filter(({ v }) => !v?.kast).map(({ e }) => e.name);
  if (missing.length) reasons.push(`Ikke vurdert av ${missing.join(" og ")}`);
  const classes = given.flatMap(({ v }) => (v?.kast ? [v.kast] : []));
  const sameClass = new Set(classes).size <= 1;
  if (!majorityNeighbour(classes)) {
    reasons.push(`For ulike klasser (${[...new Set(classes)].map((k) => KAST_LABEL[k].toLowerCase()).join(", ")})`);
  }
  const named = (test: (v: Verdict) => boolean) =>
    given.filter(({ v }) => v?.kast && test(v)).map(({ e }) => e.name).join(", ");
  const problematic = named((v) => v.problematic);
  if (problematic) reasons.push(`Problematisk: ${problematic}`);
  const doubt = named((v) => v.doubt);
  if (doubt && !sameClass) reasons.push(`Usikker og ulik klasse: ${doubt}`);
  return reasons;
}

export type Agreed = { kast: KastClass; sub: Step };

/** The auto class, or null if the corridor goes to the meeting: the middle
 *  of the experts' twelve steps (blå 0, blå +, rød − gives blå +). With
 *  majority + neighbour the middle always lies in the majority's class. */
export function agreedStep(experts: Expert[], verdicts: ExpertVerdicts, id: number): Agreed | null {
  if (!experts.length || disagreements(experts, verdicts, id).length) return null;
  const steps = experts.map((e) => stepOf(verdicts[e.id][id])).sort((a, b) => a - b);
  const mid = steps[Math.floor((steps.length - 1) / 2)];
  return { kast: CLASS_ORDER[Math.floor(mid / 3)], sub: ((mid % 3) - 1) as Step };
}

export type View = {
  /** What to show and what a change builds on. */
  consensus: Consensus;
  /** Shown from the experts' agreement; nothing stored for its class yet. */
  auto: boolean;
};

/** A corridor's consensus as the meeting sees it. A class the meeting set
 *  wins; else the auto class - unless the review took it back to
 *  discussion, which starts empty. */
export function viewOf(stored: Consensus | undefined, agreed: Agreed | null): View {
  if (stored?.kast) return { consensus: stored, auto: false };
  if (agreed && !stored?.reopened) return { consensus: { ...(stored ?? EMPTY_CONSENSUS), ...agreed }, auto: true };
  return { consensus: stored ?? EMPTY_CONSENSUS, auto: false };
}

export type Status = "agreed" | "reopened" | "settled" | "todo";

/** Auto-klassifisert / auto-overstyring / avklart i møtet / gjenstår. An
 *  auto-classified corridor stays "agreed" even if the meeting changes it
 *  afterwards; one the review took back is "reopened" until the meeting
 *  sets a class, then "settled". */
export function statusOf(stored: Consensus | undefined, agreed: Agreed | null): Status {
  if (agreed && !stored?.reopened) return "agreed";
  if (stored?.kast) return "settled";
  return agreed ? "reopened" : "todo";
}

/** Who of the experts asked for another corridor width. On an
 *  auto-classified corridor that is carried into the result as it is - not
 *  decided in the consensus, and marked so. */
export type SizeHint = { smaller: string[]; bigger: string[] };

export function sizeHint(experts: Expert[], verdicts: ExpertVerdicts, id: number): SizeHint | null {
  const who = (s: Step) => experts.filter((e) => verdicts[e.id]?.[id]?.kast && verdicts[e.id][id].size === s)
    .map((e) => e.name);
  const hint = { smaller: who(-1), bigger: who(1) };
  return hint.smaller.length || hint.bigger.length ? hint : null;
}

/** The width a hint stands for: −1, +1, or null when they pull both ways. */
export const hintSize = (h: SizeHint): Step | null =>
  h.smaller.length && h.bigger.length ? null : h.smaller.length ? -1 : 1;

export const hintLabel = (h: SizeHint): string =>
  hintSize(h) === null ? "Mindre/Større" : hintSize(h) === -1 ? "Mindre" : "Større";

/** How doubtful an auto-classification is, for the review's order. */
export type Doubt = {
  /** Two in one class, the third in the class next to it. */
  split: boolean;
  /** Highest minus lowest of the twelve steps. */
  spread: number;
  doubt: boolean;
  size: boolean;
  note: boolean;
};

export function doubtOf(experts: Expert[], verdicts: ExpertVerdicts, id: number): Doubt {
  const vs = experts.map((e) => verdicts[e.id]?.[id]).filter((v): v is Verdict => !!v?.kast);
  const steps = vs.map(stepOf);
  return {
    split: new Set(vs.map((v) => v.kast)).size > 1,
    spread: steps.length ? Math.max(...steps) - Math.min(...steps) : 0,
    doubt: vs.some((v) => v.doubt),
    size: vs.some((v) => v.size !== 0),
    note: vs.some((v) => v.note.trim() !== ""),
  };
}

/** Most doubtful first: a split class before one class, then a size asked
 *  for, then a wider spread before a narrower, then Usikker, then a note. */
export function byDoubt(a: Doubt, b: Doubt): number {
  return Number(b.split) - Number(a.split) || Number(b.size) - Number(a.size) || b.spread - a.spread
    || Number(b.doubt) - Number(a.doubt) || Number(b.note) - Number(a.note);
}

export type Filters = {
  region: string | null;
  status: "all" | Status;
};

export const NO_FILTERS: Filters = { region: null, status: "all" };

export const isFiltered = (f: Filters) => f.region !== null || f.status !== "all";

/** The corridor `step` places from `current` in `list`. One that is not in
 *  the list itself - filtered out since - steps to the nearest neighbour by
 *  id on that side instead (meant for the meeting's id order). */
export const stepFrom = (list: CorridorInfo[], current: number, step: 1 | -1): number | null => {
  if (!list.length) return null;
  const at = list.findIndex((c) => c.id === current);
  if (at >= 0) return list[at + step]?.id ?? null;
  const next = step === 1
    ? list.find((c) => c.id > current)
    : [...list].reverse().find((c) => c.id < current);
  return next?.id ?? null;
};
