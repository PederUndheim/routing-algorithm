import { API_BASE } from "./api";
import type { CorridorInfo } from "./types";

/** The static corridor files from `python -m validation_app.prepare`. */
const CORRIDORS = `${import.meta.env.BASE_URL}corridors`;

/** The track tiles are behind the access code, so they come from the API
 *  and not from Pages - see backend/server.py. */
export const trackTileUrl = (code: string, version: number) =>
  `${API_BASE}/tiles/tracks/{z}/{x}/{y}.png?code=${encodeURIComponent(code)}&v=${version}`;
export const trackIndexUrl = (code: string) =>
  `${API_BASE}/tiles/tracks/index.json?code=${encodeURIComponent(code)}`;

export const loadIndex = async (): Promise<CorridorInfo[]> => {
  const r = await fetch(`${CORRIDORS}/index.json`);
  if (!r.ok) throw new Error(`Fant ikke korridorlisten (${r.status})`);
  return r.json();
};

/** The corridor as the review drew it - see prepare.py. */
export const corridorImageUrl = (id: number) => `${CORRIDORS}/${String(id).padStart(4, "0")}.png`;

/** Start fetching a corridor image, so stepping to it draws at once. */
export const prefetchCorridor = (id: number) => {
  new Image().src = corridorImageUrl(id);
};
