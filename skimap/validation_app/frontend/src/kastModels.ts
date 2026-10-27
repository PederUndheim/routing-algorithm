import publikum from "./assets/kast/publikum.png";
import teknisk from "./assets/kast/teknisk.png";

/** The two KAST descriptions a reviewer can pull up beside the map: the
 *  public model, one line per class, and the technical one, every factor
 *  per class. Images, as the project has them. */
export type KastModel = { id: "publikum" | "teknisk"; label: string; image: string };

export const KAST_MODELS: KastModel[] = [
  { id: "publikum", label: "Publikumsmodell", image: publikum },
  { id: "teknisk", label: "Teknisk modell", image: teknisk },
];
