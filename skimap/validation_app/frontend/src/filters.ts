import { EMPTY_VERDICT, type CorridorInfo, type KastClass, type Verdict } from "./types";

/** What the corridor list is narrowed to. The arrows step through the same
 *  list, so filtering to "usikker" and pressing → walks the doubtful ones. */
export type Filters = {
  region: string | null;
  status: "all" | "todo" | "done";
  kast: KastClass | null;
  note: boolean;
  doubt: boolean;
  problematic: boolean;
};

export const NO_FILTERS: Filters = {
  region: null, status: "all", kast: null, note: false, doubt: false, problematic: false,
};

export const isFiltered = (f: Filters) =>
  f.region !== null || f.status !== "all" || f.kast !== null || f.note || f.doubt || f.problematic;

export const verdictOf = (verdicts: Record<number, Verdict>, id: number): Verdict =>
  verdicts[id] ?? EMPTY_VERDICT;

export const applyFilters = (
  corridors: CorridorInfo[], verdicts: Record<number, Verdict>, f: Filters,
): CorridorInfo[] =>
  corridors.filter((c) => {
    const v = verdictOf(verdicts, c.id);
    if (f.region !== null && c.region !== f.region) return false;
    if (f.status === "todo" && v.kast !== null) return false;
    if (f.status === "done" && v.kast === null) return false;
    if (f.kast !== null && v.kast !== f.kast) return false;
    if (f.note && !v.note.trim()) return false;
    if (f.doubt && !v.doubt) return false;
    if (f.problematic && !v.problematic) return false;
    return true;
  });

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
