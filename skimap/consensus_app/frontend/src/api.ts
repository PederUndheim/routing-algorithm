import type { Consensus, ConsensusPatch, Meeting, Verdict } from "./types";

/** Set at build time by the deploy workflow; localhost for `npm run dev`. */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "")
  ?? "http://127.0.0.1:8791";

/** Thrown for an answer from the server, as opposed to no answer at all. */
export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

const request = async <T>(code: string, method: string, path: string, body?: unknown): Promise<T> => {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    // Percent-encoded: a header cannot carry an ø as it is.
    headers: { "Content-Type": "application/json", "X-Access-Code": encodeURIComponent(code) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, payload.error ?? response.statusText);
  return payload as T;
};

export const fetchMeetings = (code: string) => request<Meeting[]>(code, "GET", "/api/meetings");

export type MeetingState = {
  meeting: string;
  /** Pass back as `since` (less a margin) to get only what changed after. */
  serverTs: string;
  consensus: Record<string, Consensus>;
};

export const fetchState = (code: string, meeting: string, since?: string) =>
  request<MeetingState>(code, "GET",
    `/api/state?meeting=${encodeURIComponent(meeting)}${since ? `&since=${encodeURIComponent(since)}` : ""}`);

export type ExpertState = {
  meeting: string;
  /** expert id -> corridor id -> verdict */
  verdicts: Record<string, Record<string, Verdict>>;
};

export const fetchExperts = (code: string, meeting: string) =>
  request<ExpertState>(code, "GET", `/api/experts?meeting=${encodeURIComponent(meeting)}`);

export type Op = {
  opId: string;
  meeting: string;
  corridor: number;
  patch: ConsensusPatch;
  clientTs: string;
};

export const sendOp = (code: string, op: Op) =>
  request<{ corridor: number; consensus: Consensus }>(code, "POST", "/api/consensus", op);

export const resetTestMeeting = (code: string) =>
  request<{ removed: number }>(code, "POST", "/api/reset", { meeting: "test" });
