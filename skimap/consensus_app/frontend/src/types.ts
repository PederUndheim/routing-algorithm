export type KastClass = "green" | "blue" | "red" | "black";
export type Step = -1 | 0 | 1;

/** One expert's verdict from the validation app - read-only here. */
export type Verdict = {
  kast: KastClass | null;
  sub: Step;
  size: Step;
  note: string;
  doubt: boolean;
  problematic: boolean;
  updatedAt?: string;
};

/** What the meeting decides about one corridor - see backend/consensus.py. */
export type Consensus = {
  kast: KastClass | null;
  size: Step;
  problematic: boolean;
  /** What should be changed before it can be published. */
  change: string;
  /** The meeting's common comment. */
  note: string;
  updatedAt?: string;
};

export type ConsensusPatch = Partial<Omit<Consensus, "updatedAt">>;

export const EMPTY_CONSENSUS: Consensus = {
  kast: null, size: 0, problematic: false, change: "", note: "",
};

export type Expert = { id: string; name: string };

export type Meeting = {
  id: string;
  date: string;
  label: string;
  experts: Expert[];
  corridorsOf: string;
  corridors: number[];
  test?: boolean;
};

/** One row of public/corridors/index.json (the validation app's). */
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

export const SUB_MARK: Record<Step, string> = { [-1]: " −", 0: "", 1: " +" };
