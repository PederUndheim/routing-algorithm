import type { LatLng, RouteResponse } from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Absolute URL for a path the API handed back, such as a corridor PNG. */
export const apiUrl = (path: string): string => `${BASE}${path}`;

/** Wake the backend and report whether it answered.
 *
 * Starting GRASS takes a few seconds, so the panel says so rather than
 * letting the first route look like a hang. */
export const checkHealth = async (): Promise<boolean> => {
  try {
    const res = await fetch(`${BASE}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
};

export const requestRoute = async (
  start: LatLng,
  end: LatLng
): Promise<RouteResponse> => {
  const res = await fetch(`${BASE}/route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ start, end }),
  });

  // The backend puts its reason in `message` on every 4xx, so prefer that
  // over the status code - "sits outside the cost surface" is worth showing.
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.message ?? `Routing failed (HTTP ${res.status}).`);
  }
  return data as RouteResponse;
};
