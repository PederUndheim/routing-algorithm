import type {
  Answers,
  Crux,
  CruxProblem,
  CruxSegment,
  Factor,
  Hazards,
  Rating,
} from "../types";

/** What an info icon explains: the question, then what pushes the rating
 *  towards a thumb up and towards a thumb down. */
export type RatingInfo = { question: string; up: string; down: string };

/** The aspects of a Crux the user weighs up, in the order they are asked.
 *  Each is an open question rather than a yes/no, rated from clearly in the
 *  user's favour to clearly against them. They are kept apart on purpose:
 *  slope size is the terrain, release volume is today's snow, terrain traps
 *  are what happens if caught, safe spots are how exposed you are, and
 *  remote triggering is whether you can set it off without being on it. */
export const QUESTIONS: ({ factor: Factor; title: string } & RatingInfo)[] = [
  {
    factor: "slope_size",
    title: "Slope size",
    question:
      "How big is the steep slope you are exposed to - its height, width, and how far a slide could carry you?",
    up: "A short, small slope. A slide would be small and stop quickly.",
    down: "A long or wide slope with a long run below. A slide could carry you far and bury you.",
  },
  {
    factor: "release_volume",
    title: "Release volume",
    question:
      "How much snow could come loose here today - consider new snow, wind-loaded snow, and how deep a weak layer lies?",
    up: "Little loose snow, thin layers, nothing wind-loaded. At most a small sluff.",
    down: "Deep or wind-loaded snow over a weak layer. A thick slab that could break wide.",
  },
  {
    factor: "terrain_traps",
    title: "Terrain traps",
    question:
      "What lies below and around - would being caught be made worse by the terrain?",
    up: "Smooth, open runout where a slide spreads out and stops.",
    down: "A gully or hollow where snow piles deep, cliffs or rocks, trees, or open water.",
  },
  {
    factor: "safe_spots",
    title: "Safe spots",
    question:
      "Can you limit your exposure - stop, regroup and cross one at a time out of reach of the slope?",
    up: "Short exposure, with safe spots before and after to cross one at a time and watch.",
    down: "Long exposure with nowhere safe to stop, or no way to space the group out.",
  },
  {
    factor: "remote_triggering",
    title: "Remote triggering",
    question:
      "How likely is it, in today's snowpack and conditions, that the slope above or beside you is set off from a distance - from where you travel, not on the slope itself?",
    up: "A well-bonded snowpack with no persistent weak layer, no persistent slab problem in the forecast, and no signs of instability.",
    down: "A known persistent weak layer or persistent slab problem in the forecast, or whumpfs, shooting cracks or recent avalanches nearby.",
  },
];

/** A snow conditions check has no aspects to rate: the overall rating is
 *  what the snow told the user there. */
export const SNOW_CHECK_INFO: RatingInfo = {
  question:
    "What did the snow tell you here - layers, tests, signs of instability? Weigh it together with today's avalanche forecast.",
  up: "A well-bonded snowpack, no worrying layers, and no cracking or collapsing.",
  down: "Weak layers, cracking or whumpfs, or test results that point to instability.",
};

/** What the overall verdict asks for: the user's own weighing, not a count. */
export const OVERALL_INFO: RatingInfo = {
  question:
    "Weighing it all up with today's avalanche forecast and what you see - how does this crux look? One aspect clearly against you can outweigh several in your favour.",
  up: "Acceptable as planned.",
  down: "Critical - choose another line, another time, or turn back.",
};

/** A Runout area is the flatter ground below a slope: it only slides when set
 *  off from the steeper ground above, so remote triggering is all there is to
 *  weigh. Everything else - 30° and steeper - gets all five. */
export const questionsFor = (crux: Pick<Crux, "class" | "snow_check">) =>
  crux.snow_check
    ? []
    : crux.class === "runout_area"
      ? QUESTIONS.filter((q) => q.factor === "remote_triggering")
      : QUESTIONS;

/** The five ratings, in the order they are offered: what each is called -
 *  the same for an aspect, an overall rating and a snow check - and its
 *  colour. The colour carries the step - dark and light at each end - since
 *  thumbs of two sizes are hard to tell apart at button size. */
export const RATINGS: {
  id: Rating;
  label: string;
  color: string;
  /** Which way the thumb points, if any, and whether it is the big one. */
  thumb: "up" | "down" | null;
  strong: boolean;
}[] = [
  { id: "very_good", label: "Very positive", color: "#1B7F3B", thumb: "up", strong: true },
  { id: "good", label: "Positive", color: "#66BB6A", thumb: "up", strong: false },
  { id: "neutral", label: "No effect", color: "#8C8C8C", thumb: null, strong: false },
  { id: "bad", label: "Negative", color: "#E57373", thumb: "down", strong: false },
  { id: "very_bad", label: "Very negative", color: "#C62828", thumb: "down", strong: true },
];

export const ratingOf = (id: Rating) => RATINGS.find((r) => r.id === id)!;

/** A Runout area is asked only one thing, so its one rating is its overall
 *  rating too - asking for the same judgement twice would only be noise.
 *  Everything else has the overall the user gave it. */
export const hasOwnOverall = (crux: Pick<Crux, "class" | "snow_check">): boolean =>
  questionsFor(crux).length !== 1;

export const overallOf = (
  crux: Pick<Crux, "class" | "snow_check"> & { answers: Answers; overall?: Rating }
): Rating | undefined => (hasOwnOverall(crux) ? crux.overall : crux.answers.remote_triggering);

/** The user has evaluated the Crux and chosen to keep it. Until then it is
 *  drawn with a dashed border, as still to be done; one not kept is off the
 *  list and the map altogether. */
export const isDecided = (crux: { keep?: boolean }): boolean => crux.keep === true;

/** What a marker and a list row say about the user's evaluation: the
 *  overall rating of a Crux they have kept, "kept" for one kept without a
 *  rating, or null while it is still to be evaluated. */
export type Verdict = Rating | "kept" | null;

export const verdictOf = (
  crux: Pick<Crux, "class" | "snow_check"> & { answers: Answers; overall?: Rating; keep?: boolean }
): Verdict => (isDecided(crux) ? (overallOf(crux) ?? "kept") : null);

/** Rated against the user overall - either step - which is what the map
 *  and its clusters call critical. */
export const isCritical = (overall: Rating | undefined): boolean =>
  overall === "bad" || overall === "very_bad";

/** Where a Crux lives in the list, and whether it is on the map:
 *  - active: kept, or not decided yet - listed and drawn
 *  - not_kept: the user chose to take it out of the list - greyed out, not drawn
 *  - deleted: deleted by the user - greyed out below those, not drawn
 *
 *  The overall rating is the user's own reading, shown with the Crux; it is
 *  the keep choice that decides where it goes. */
export type CruxShelf = "active" | "not_kept" | "deleted";

export const shelfOf = (crux: { keep?: boolean; deleted?: boolean }): CruxShelf => {
  if (crux.deleted) return "deleted";
  return crux.keep === false ? "not_kept" : "active";
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
    case "snow_check":
      return { class: "steep_slope", snow_check: true };
  }
};

/** The symbol a Crux is drawn with, as one of the problems a user can pick.
 *  An identified area can be a release area and a fall hazard at once; it
 *  reads as a release area here, which is what it is named first. */
export const problemOf = (crux: Hazards & { class: Crux["class"] }): CruxProblem => {
  if (crux.snow_check) return "snow_check";
  if (crux.class === "runout_area") return "runout_area";
  if (crux.probable_release_area) return "release_area";
  if (crux.fall_hazard) return "fall_hazard";
  return "steep_slope";
};

/** What the analysed line says at a point along it, as a starting point for
 *  a Crux placed there by hand: the problem it is drawn with. Steep slope
 *  where nothing is known, so it gets all the questions. */
export const defaultsAt = (
  segments: readonly CruxSegment[] | undefined,
  distance_m: number
): { problem: CruxProblem } => {
  const segment = segments?.find((s) => s.start_m <= distance_m && distance_m <= s.end_m);
  if (segment?.class === "runout_area") return { problem: "runout_area" };
  if (segment?.class !== "steep_slope") return { problem: "steep_slope" };
  return {
    problem: segment.probable_release_area
      ? "release_area"
      : segment.fall_hazard
        ? "fall_hazard"
        : "steep_slope",
  };
};
