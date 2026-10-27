import { ApiError, type Op } from "./api";
import type { VerdictPatch } from "./types";

/** Every change a reviewer makes, on its way to the server.
 *
 *  The queue is the reason a click is never lost. A change is written to
 *  localStorage before anything is sent, so a closed tab, a dropped network
 *  or a cold-starting backend only delays it: the queue is read back on the
 *  next load and sent then. Ops go one at a time, in order, and each is
 *  retried until the server says yes - with the same opId, so a retry of a
 *  write that did land is recognised and not recorded twice.
 *
 *  Typing a note would otherwise be one op per keystroke. A new patch for the
 *  same user and corridor as the op waiting at the tail is merged into it
 *  instead, as long as that op has not been sent yet.
 *
 *  A 4xx other than 401 is a request that can never succeed; it is dropped
 *  and reported rather than retried forever behind everything else. A 401
 *  means the access code changed, and the op is kept for when it is fixed.
 */

export type SaveStatus =
  | { kind: "saved" }
  | { kind: "saving"; pending: number }
  | { kind: "retrying"; pending: number; message: string }
  | { kind: "unauthorized"; pending: number }
  | { kind: "error"; message: string };

type Sender = (op: Op) => Promise<unknown>;

const STORAGE_KEY = "validering.queue.v1";
const MAX_BACKOFF_MS = 30_000;

const newOpId = () =>
  Array.from(crypto.getRandomValues(new Uint8Array(12)), (b) => b.toString(16).padStart(2, "0")).join("");

export class SaveQueue {
  private ops: Op[];
  private inFlight: Op | null = null;
  /** Ops that have been sent at least once, and so may already be on the
   *  server under their opId: never merged into. Everything read back from
   *  storage counts, since the last page may have sent it. */
  private attempted = new Set<string>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private backoff = 1000;
  private stopped = false;
  private status: SaveStatus = { kind: "saved" };
  private listeners = new Set<(s: SaveStatus) => void>();

  constructor(private send: Sender, private storage: Storage | null = safeStorage()) {
    this.ops = this.load();
    this.ops.forEach((op) => this.attempted.add(op.opId));
  }

  get pending(): readonly Op[] {
    return this.ops;
  }

  subscribe(listener: (s: SaveStatus) => void): () => void {
    this.listeners.add(listener);
    listener(this.status);
    return () => this.listeners.delete(listener);
  }

  /** Queue a change; `delayMs` holds the send back, for typing. */
  push(user: string, corridor: number, patch: VerdictPatch, delayMs = 0): void {
    const tail = this.ops[this.ops.length - 1];
    if (tail && !this.attempted.has(tail.opId) && tail.user === user && tail.corridor === corridor) {
      tail.patch = { ...tail.patch, ...patch };
      tail.clientTs = new Date().toISOString();
    } else {
      this.ops.push({ opId: newOpId(), user, corridor, patch, clientTs: new Date().toISOString() });
    }
    this.save();
    this.schedule(delayMs);
  }

  /** Send now whatever is waiting - on navigation, blur, coming back online. */
  flush(): void {
    this.schedule(0);
  }

  /** No more sending from this instance; what is queued stays in storage. */
  stop(): void {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  private schedule(delayMs: number): void {
    if (this.inFlight || this.stopped) return; // the running send picks up the rest
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.run();
    }, delayMs);
    if (this.ops.length) this.setStatus({ kind: "saving", pending: this.ops.length });
  }

  private async run(): Promise<void> {
    let rejected: string | null = null;
    while (this.ops.length && !this.inFlight) {
      const op = this.ops[0];
      this.inFlight = op;
      this.attempted.add(op.opId);
      this.setStatus({ kind: "saving", pending: this.ops.length });
      try {
        await this.send(op);
        this.ops.shift();
        this.backoff = 1000;
        this.save();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          this.inFlight = null;
          this.setStatus({ kind: "unauthorized", pending: this.ops.length });
          return;
        }
        if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
          this.ops.shift();
          this.save();
          this.inFlight = null;
          rejected = `Endring avvist: ${e.message}`;
          continue;
        }
        this.inFlight = null;
        this.setStatus({
          kind: "retrying",
          pending: this.ops.length,
          message: e instanceof Error ? e.message : String(e),
        });
        if (this.stopped) return;
        this.timer = setTimeout(() => {
          this.timer = null;
          void this.run();
        }, this.backoff);
        this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF_MS);
        return;
      }
      this.inFlight = null;
    }
    if (!this.ops.length) this.setStatus(rejected ? { kind: "error", message: rejected } : { kind: "saved" });
  }

  private setStatus(status: SaveStatus): void {
    this.status = status;
    this.listeners.forEach((l) => l(status));
  }

  private load(): Op[] {
    try {
      const raw = this.storage?.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as Op[]) : [];
    } catch {
      return [];
    }
  }

  private save(): void {
    try {
      this.storage?.setItem(STORAGE_KEY, JSON.stringify(this.ops));
    } catch {
      // Private mode or a full quota: the queue still works for this tab.
    }
  }
}

function safeStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}
