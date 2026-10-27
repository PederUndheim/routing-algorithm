import type { User, Verdict, VerdictPatch } from "./types";

/** Set at build time by the deploy workflow; localhost for `npm run dev`. */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "")
  ?? "http://127.0.0.1:8790";

/** Thrown for an answer from the server, as opposed to no answer at all. */
export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

const request = async <T>(code: string, method: string, path: string, body?: unknown): Promise<T> => {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    // Percent-encoded: a header cannot carry an ø as it is - see server.py.
    headers: { "Content-Type": "application/json", "X-Access-Code": encodeURIComponent(code) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, payload.error ?? response.statusText);
  return payload as T;
};

export const fetchUsers = (code: string) => request<User[]>(code, "GET", "/api/users");

export type UserState = {
  user: string;
  /** null: every corridor. */
  assigned: number[] | null;
  verdicts: Record<string, Verdict>;
};

export const fetchState = (code: string, user: string) =>
  request<UserState>(code, "GET", `/api/state?user=${encodeURIComponent(user)}`);

export type Op = {
  opId: string;
  user: string;
  corridor: number;
  patch: VerdictPatch;
  clientTs: string;
};

export const sendOp = (code: string, op: Op) =>
  request<{ corridor: number; verdict: Verdict }>(code, "POST", "/api/verdict", op);

export const resetTestUser = (code: string) =>
  request<{ removed: number }>(code, "POST", "/api/reset", { user: "test" });
