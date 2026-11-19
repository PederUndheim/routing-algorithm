import {
  EMPTY_CONSENSUS, KAST_LABEL, type Consensus, type CorridorInfo, type Expert,
  type KastClass, type Step, type Verdict,
} from "./types";

/** expert id -> corridor id -> verdict */
export type ExpertVerdicts = Record<string, Record<number, Verdict>>;

/** Why the experts do not simply agree, one line each; empty when they do.
 *
 *  Agreed - and so done before the meeting starts - means: every expert in
 *  the meeting has set a class, all the same main class (−/0/+ ignored), all
 *  left the size at OK, and nobody ticked Usikker or Problematisk. Notes do
 *  not count; they are shown, but do not stop it. */
export function disagreements(experts: Expert[], verdicts: ExpertVerdicts, id: number): string[] {
  const reasons: string[] = [];
  const given = experts.map((e) => ({ e, v: verdicts[e.id]?.[id] }));
  const missing = given.filter(({ v }) => !v?.kast).map(({ e }) => e.name);
  if (missing.length) reasons.push(`Ikke vurdert av ${missing.join(" og ")}`);
  const classes = new Set(given.flatMap(({ v }) => (v?.kast ? [v.kast] : [])));
  if (classes.size > 1) {
    reasons.push(`Ulik klasse (${[...classes].map((k) => KAST_LABEL[k].toLowerCase()).join(", ")})`);
  }
  const named = (test: (v: Verdict) => boolean) =>
    given.filter(({ v }) => v && test(v)).map(({ e }) => e.name).join(", ");
  const size = named((v) => v.size !== 0);
  if (size) reasons.push(`Størrelse: ${size}`);
  const problematic = named((v) => v.problematic);
  if (problematic) reasons.push(`Problematisk: ${problematic}`);
  const doubt = named((v) => v.doubt);
  if (doubt) reasons.push(`Usikker: ${doubt}`);
  return reasons;
}

export type Agreed = { kast: KastClass; sub: Step };

/** What the experts agree on, or null if they do not quite: their class, and
 *  as the step within it the middle of theirs (−, 0, + gives 0; 0, +, +
 *  gives +). The step does not decide agreement; the main class does. */
export function agreedStep(experts: Expert[], verdicts: ExpertVerdicts, id: number): Agreed | null {
  if (!experts.length || disagreements(experts, verdicts, id).length) return null;
  const subs = experts.map((e) => verdicts[e.id][id].sub).sort((a, b) => a - b);
  return { kast: verdicts[experts[0].id][id].kast as KastClass, sub: subs[Math.floor((subs.length - 1) / 2)] };
}

export type View = {
  /** What to show and what a change builds on. */
  consensus: Consensus;
  /** Shown from the experts' agreement; nothing stored for its class yet. */
  auto: boolean;
};

/** A corridor's consensus as the meeting sees it. A class the meeting set
 *  wins; else, if the experts agree, theirs. */
export function viewOf(stored: Consensus | undefined, agreed: Agreed | null): View {
  if (stored?.kast) return { consensus: stored, auto: false };
  if (agreed) return { consensus: { ...(stored ?? EMPTY_CONSENSUS), ...agreed }, auto: true };
  return { consensus: stored ?? EMPTY_CONSENSUS, auto: false };
}

export type Status = "agreed" | "settled" | "todo";

/** Enige fra start / avklart i møtet / gjenstår. A corridor the experts
 *  agreed on stays "agreed" even if the meeting changes it afterwards. */
export const statusOf = (stored: Consensus | undefined, agreed: Agreed | null): Status =>
  agreed ? "agreed" : stored?.kast ? "settled" : "todo";

export type Filters = {
  region: string | null;
  status: "all" | Status;
  problematic: boolean;
};

export const NO_FILTERS: Filters = { region: null, status: "all", problematic: false };

export const isFiltered = (f: Filters) => f.region !== null || f.status !== "all" || f.problematic;

/** The corridor `step` places from `current` in `list` (by id order). One
 *  that is not in the list itself - filtered out since - steps to the
 *  nearest neighbour on that side instead. */
export const stepFrom = (list: CorridorInfo[], current: number, step: 1 | -1): number | null => {
  if (!list.length) return null;
  const at = list.findIndex((c) => c.id === current);
  if (at >= 0) return list[at + step]?.id ?? null;
  const next = step === 1
    ? list.find((c) => c.id > current)
    : [...list].reverse().find((c) => c.id < current);
  return next?.id ?? null;
};
