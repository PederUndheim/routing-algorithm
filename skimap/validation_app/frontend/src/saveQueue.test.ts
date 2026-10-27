import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type Op } from "./api";
import { SaveQueue, type SaveStatus } from "./saveQueue";

class MemoryStorage implements Storage {
  private data = new Map<string, string>();
  get length() { return this.data.size; }
  clear() { this.data.clear(); }
  getItem(k: string) { return this.data.get(k) ?? null; }
  key(i: number) { return [...this.data.keys()][i] ?? null; }
  removeItem(k: string) { this.data.delete(k); }
  setItem(k: string, v: string) { this.data.set(k, v); }
}

describe("SaveQueue", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("sends ops in order and ends saved", async () => {
    const sent: Op[] = [];
    const q = new SaveQueue(async (op) => { sent.push(op); }, new MemoryStorage());
    let status: SaveStatus | null = null;
    q.subscribe((s) => (status = s));
    q.push("finn", 1, { kast: "red" });
    q.push("finn", 2, { kast: "blue" });
    await vi.runAllTimersAsync();
    expect(sent.map((o) => o.corridor)).toEqual([1, 2]);
    expect(status).toEqual({ kind: "saved" });
  });

  it("merges typing into the unsent tail op", async () => {
    const sent: Op[] = [];
    const q = new SaveQueue(async (op) => { sent.push(op); }, new MemoryStorage());
    q.push("finn", 1, { note: "b" }, 500);
    q.push("finn", 1, { note: "br" }, 500);
    q.push("finn", 1, { note: "bra" }, 500);
    await vi.runAllTimersAsync();
    expect(sent).toHaveLength(1);
    expect(sent[0].patch).toEqual({ note: "bra" });
  });

  it("retries with the same opId and never merges into a tried op", async () => {
    const sent: Op[] = [];
    let fail = true;
    const q = new SaveQueue(async (op) => {
      sent.push(structuredClone(op));
      if (fail) throw new TypeError("Failed to fetch");
    }, new MemoryStorage());
    q.push("finn", 1, { kast: "red" });
    await vi.advanceTimersByTimeAsync(0);
    q.push("finn", 1, { sub: 1 });
    fail = false;
    await vi.runAllTimersAsync();
    expect(sent.map((o) => o.patch)).toEqual([{ kast: "red" }, { kast: "red" }, { sub: 1 }]);
    expect(sent[0].opId).toBe(sent[1].opId);
    expect(sent[2].opId).not.toBe(sent[0].opId);
  });

  it("keeps unsent ops across a reload", async () => {
    const storage = new MemoryStorage();
    const offline = new SaveQueue(async () => { throw new TypeError("offline"); }, storage);
    offline.push("markus", 7, { kast: "black" });
    await vi.advanceTimersByTimeAsync(0);
    offline.stop(); // the tab is closed

    const sent: Op[] = [];
    const reloaded = new SaveQueue(async (op) => { sent.push(op); }, storage);
    expect(reloaded.pending).toHaveLength(1);
    reloaded.flush();
    await vi.runAllTimersAsync();
    expect(sent[0].patch).toEqual({ kast: "black" });
    expect(reloaded.pending).toHaveLength(0);
  });

  it("drops a rejected op but stops on a wrong access code", async () => {
    const q = new SaveQueue(async (op) => {
      if (op.corridor === 1) throw new ApiError(400, "bad");
      throw new ApiError(401, "wrong code");
    }, new MemoryStorage());
    let status: SaveStatus | null = null;
    q.subscribe((s) => (status = s));
    q.push("finn", 1, { kast: "red" });
    q.push("finn", 2, { kast: "red" });
    await vi.runAllTimersAsync();
    expect(q.pending.map((o) => o.corridor)).toEqual([2]);
    expect(status).toEqual({ kind: "unauthorized", pending: 1 });
  });
});
