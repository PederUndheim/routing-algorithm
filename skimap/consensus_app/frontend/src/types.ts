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
  /** The −/0/+ within the class, as in the validation. */
  sub: Step;
  size: Step;
  /** The meeting chose the width - so the experts' width on an auto
   *  corridor no longer stands in for it, even when it chose OK. */
  sizeSet: boolean;
  /** The review of the auto-classification took it back to discussion. */
  reopened: boolean;
  /** No longer set in the meeting (the button was removed 2026-11-19). */
  problematic: boolean;
  /** What should be changed before publishing - went with the flag. */
  change: string;
  /** The meeting's common comment. */
  note: string;
  /** To do with the corridor later: add a waypoint, and where. */
  midpoint: boolean;
  midpointWhere: string;
  /** Move the end point, and where to. */
  endpoint: boolean;
  endpointWhere: string;
  /** Anything else to do, and what. */
  other: boolean;
  otherWhat: string;
  /** The corridor should be deleted. */
  remove: boolean;
  /** Split it into two tours: where each goes and its class. */
  split: boolean;
  split1Where: string;
  split1Kast: KastClass | null;
  split1Sub: Step;
  split2Where: string;
  split2Kast: KastClass | null;
  split2Sub: Step;
  updatedAt?: string;
};

export type ConsensusPatch = Partial<Omit<Consensus, "updatedAt">>;

export const EMPTY_CONSENSUS: Consensus = {
  kast: null, sub: 0, size: 0, sizeSet: false, problematic: false, change: "", note: "",
  midpoint: false, midpointWhere: "", endpoint: false, endpointWhere: "",
  other: false, otherWhat: "", remove: false, reopened: false,
  split: false, split1Where: "", split1Kast: null, split1Sub: 0, split2Where: "", split2Kast: null, split2Sub: 0,
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
