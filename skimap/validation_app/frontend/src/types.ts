export type KastClass = "green" | "blue" | "red" | "black";
export type Step = -1 | 0 | 1;

/** One reviewer's verdict on one corridor - see backend/verdicts.py. */
export type Verdict = {
  kast: KastClass | null;
  sub: Step;
  size: Step;
  note: string;
  doubt: boolean;
  problematic: boolean;
  updatedAt?: string;
};

export type VerdictPatch = Partial<Omit<Verdict, "updatedAt">>;

export const EMPTY_VERDICT: Verdict = {
  kast: null, sub: 0, size: 0, note: "", doubt: false, problematic: false,
};

export type User = { id: string; name: string };

/** One row of public/corridors/index.json. */
export type CorridorInfo = {
  id: number;
  region: string;
  regionId: number | null;
  lengthM: number;
  /** The corridor image's bounds: west, south, east, north. */
  bbox: [number, number, number, number];
};

export const KAST_CLASSES: KastClass[] = ["green", "blue", "red", "black"];

export const KAST_LABEL: Record<KastClass, string> = {
  green: "Grønn", blue: "Blå", red: "Rød", black: "Svart",
};

export const KAST_COLOUR: Record<KastClass, string> = {
  green: "#2f9e44", blue: "#1c6dd0", red: "#d9302c", black: "#1d1d1f",
};
