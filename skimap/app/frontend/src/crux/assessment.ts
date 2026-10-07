import type {
  Answers,
  Crux,
  CruxProblem,
  CruxSegment,
  Factor,
  Hazards,
  SlopeCategory,
} from "../types";

export const SLOPE_CATEGORIES: { id: SlopeCategory; label: string }[] = [
  { id: "lt30", label: "<30°" },
  { id: "30_34", label: "30-34°" },
  { id: "35_39", label: "35-39°" },
  { id: "gt39", label: ">39°" },
];

export const categoryLabel = (category: SlopeCategory): string =>
  SLOPE_CATEGORIES.find((c) => c.id === category)!.label;

/** The category of a slope in degrees. */
export const categoryOfSlope = (degrees: number): SlopeCategory => {
  if (degrees < 30) return "lt30";
  if (degrees < 35) return "30_34";
  if (degrees < 40) return "35_39";
  return "gt39";
};

/** An identified Crux's category, from the steepest ground in its area. A
 *  Runout area is the flatter ground below a slope, so it is under 30. */
export const categoryOfCrux = (crux: Pick<Crux, "class" | "max_slope_deg">): SlopeCategory => {
  if (crux.class !== "steep_slope") return "lt30";
  // Steep slope starts at 30, so one with no reading is at least that.
  return categoryOfSlope(crux.max_slope_deg ?? 30);
};

/** The questions, in the order they are asked. A yes is always the more
 *  serious answer, so counting them is all the rules below need. */
export const QUESTIONS: { factor: Factor; title: string; text: string }[] = [
  {
    factor: "slope_size",
    title: "Slope size",
    text: "Is the slope big enough to matter - could a slide here bury or injure you?",
  },
  {
    factor: "release_volume",
    title: "Release volume",
    text: "Could a slide here release a large volume of snow?",
  },
  {
    factor: "terrain_traps",
    title: "Terrain traps",
    text: "Are there terrain traps below - a gully, cliff, trees or a lake that make being caught worse?",
  },
  {
    factor: "safe_spots",
    title: "Safe spots",
    text: "Is it hard to find a safe spot - nowhere to stop or regroup out of reach of the slope?",
  },
  {
    factor: "remote_triggering",
    title: "Remote triggering",
    text: "Could the slope be triggered from a distance - from below, beside or above it?",
  },
];

/** Under 30 only remote triggering matters: gentle ground slides only when
 *  set off from steeper ground nearby. */
export const questionsFor = (category: SlopeCategory) =>
  category === "lt30" ? QUESTIONS.filter((q) => q.factor === "remote_triggering") : QUESTIONS;

/** Where a Crux stands once the user has answered about it:
 *  - unassessed: not enough answered to say anything yet
 *  - kept: still a Crux, not critical
 *  - critical: kept, and highlighted
 *  - dismissed: answered as not relevant, so off the map */
export type CruxStatus = "unassessed" | "kept" | "critical" | "dismissed";

/** How many yes answers make a Crux critical where the answers decide it. */
const CRITICAL_AT: Partial<Record<SlopeCategory, number>> = { "30_34": 2, "35_39": 1 };

export const assess = (category: SlopeCategory, answers: Answers): CruxStatus => {
  if (category === "gt39") return "critical";

  if (category === "lt30") {
    const remote = answers.remote_triggering;
    if (remote === undefined) return "unassessed";
    return remote ? "kept" : "dismissed";
  }

  const yes = QUESTIONS.filter((q) => answers[q.factor] === true).length;
  if (yes >= CRITICAL_AT[category]!) return "critical";
  const answered = QUESTIONS.every((q) => answers[q.factor] !== undefined);
  return answered ? "kept" : "unassessed";
};

/** The rule for a category, in words, for under the questions. */
export const ruleText = (category: SlopeCategory): string => {
  switch (category) {
    case "lt30":
      return "Yes keeps the crux; no dismisses it.";
    case "30_34":
      return "Two or more yes makes it critical.";
    case "35_39":
      return "One or more yes makes it critical.";
    case "gt39":
      return "Steeper than 39° - always critical.";
  }
};

/** A hand-placed Crux's problem as the class and marks the identifier would
 *  have given it, so it is named and drawn the same way. */
export const problemHazards = (problem: CruxProblem): Hazards & { class: Crux["class"] } => {
  switch (problem) {
    case "steep_slope":
      return { class: "steep_slope" };
    case "release_area":
      return { class: "steep_slope", probable_release_area: true };
    case "fall_hazard":
      return { class: "steep_slope", fall_hazard: true };
    case "runout_area":
      return { class: "runout_area" };
  }
};

/** What the analysed line says at a point along it, as a starting point for
 *  a Crux placed there by hand. Null category where nothing is known - no
 *  analysis, or no terrain data - so the user has to choose one. */
export const defaultsAt = (
  segments: readonly CruxSegment[] | undefined,
  distance_m: number
): { category: SlopeCategory | null; problem: CruxProblem } => {
  const segment = segments?.find((s) => s.start_m <= distance_m && distance_m <= s.end_m);
  if (!segment || segment.class === "no_data") return { category: null, problem: "steep_slope" };
  if (segment.class === "runout_area") return { category: "lt30", problem: "runout_area" };
  if (segment.class === "none") return { category: "lt30", problem: "steep_slope" };
  return {
    category: categoryOfSlope(segment.max_slope_deg ?? 30),
    problem: segment.probable_release_area
      ? "release_area"
      : segment.fall_hazard
        ? "fall_hazard"
        : "steep_slope",
  };
};
