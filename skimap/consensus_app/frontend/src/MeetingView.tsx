import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchExperts, fetchState, resetTestMeeting } from "./api";
import {
  NO_FILTERS, agreedStep, byDoubt, doubtOf, sizeHint, statusOf, stepFrom, viewOf,
  type ExpertVerdicts, type Filters, type Status, type View,
} from "./agreement";
import { CorridorList } from "./CorridorList";
import { prefetchCorridor } from "./data";
import { ExpertsColumn } from "./ExpertsColumn";
import { ChevronLeft, ChevronRight, CloseIcon, KeyboardIcon, ListIcon } from "./icons";
import type { KastModel } from "./kastModels";
import type { BasemapId, SteepnessId } from "./layers";
import { MapView } from "./MapView";
import {
  FollowUpPanel, KastPanel, LayerPanel, ModelImage, NotesPanel, ReviewPanel, ShortcutHelp, SizePanel,
} from "./panels";
import type { SaveQueue, SaveStatus } from "./saveQueue";
import {
  EMPTY_CONSENSUS, type Consensus, type ConsensusPatch, type CorridorInfo,
  KAST_CLASSES, type KastClass, type Meeting, type Step, type Verdict,
} from "./types";

type Props = {
  code: string;
  meeting: Meeting;
  index: CorridorInfo[];
  queue: SaveQueue;
  status: SaveStatus;
  onLeave: () => void;
  /** The review of the auto-classification: only the auto-classified
   *  corridors, most doubtful first, and one thing to decide - whether to
   *  take each back to discussion. */
  review?: boolean;
};

type MapSettings = { basemap: BasemapId; steepness: SteepnessId | null; tracks: boolean; opacity: number };
const DEFAULT_MAP: MapSettings = { basemap: "topo", steepness: "bratthet", tracks: false, opacity: 0.3 };
const MAP_KEY = "konsensus.map.v1";

const remembered = <T,>(key: string, fallback: T): T => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
};
const remember = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // only a convenience
  }
};

const TEXT_DELAY_MS = 800;
/** How often to ask what the others in the meeting have changed. */
const POLL_MS = 4000;
/** How often to re-read the experts' verdicts (live from the validation). */
const EXPERTS_MS = 30_000;
/** Each poll asks for rows changed since the last answer less this, so a
 *  write that was in flight during that answer is not missed. */
const OVERLAP_MS = 15_000;

/** As in the validation app: one keyboard row per class, top to bottom green
 *  to black, and left to right − 0 +. */
const KAST_KEYS: Record<string, [KastClass, Step]> = Object.fromEntries(
  (["123", "qwe", "asd", "zxc"] as const).flatMap((row, i) =>
    [...row].map((key, j) => [key, [KAST_CLASSES[i], (j - 1) as Step]])),
);

const minus = (ts: string, ms: number) => new Date(Date.parse(ts) - ms).toISOString().replace("Z", "+00:00");

export function MeetingView({ code, meeting, index, queue, status, onLeave, review = false }: Props) {
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [syncError, setSyncError] = useState(false);
  const [stored, setStored] = useState<Record<number, Consensus>>({});
  const [experts, setExperts] = useState<ExpertVerdicts | null>(null);
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [listOpen, setListOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [model, setModel] = useState<KastModel | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [mapSettings, setMapSettings] = useState<MapSettings>(() => remembered(MAP_KEY, DEFAULT_MAP));
  const lastKey = `konsensus.${review ? "review" : "last"}.${meeting.id}`;
  const since = useRef<string | null>(null);

  // --- load, and keep up with the others ---------------------------------------

  /** Rows from the server into what is shown. A row no newer than the one
   *  held is an answer that left before a change made here landed, and is
   *  skipped. Changes still in the queue go on top, so typing is never
   *  overwritten by a poll. */
  const merge = useCallback((rows: Record<string, Consensus>, replace: boolean) => {
    setStored((prev) => {
      const next = replace ? {} : { ...prev };
      for (const [key, row] of Object.entries(rows)) {
        const id = Number(key);
        const held = next[id];
        if (!replace && held?.updatedAt && row.updatedAt && row.updatedAt <= held.updatedAt) continue;
        next[id] = row;
      }
      for (const op of queue.pending) {
        if (op.meeting === meeting.id) next[op.corridor] = { ...(next[op.corridor] ?? EMPTY_CONSENSUS), ...op.patch };
      }
      return next;
    });
  }, [queue, meeting.id]);

  const load = useCallback(() => {
    setLoadError(null);
    fetchState(code, meeting.id).then((state) => {
      merge(state.consensus, true);
      since.current = state.serverTs;
      setLoaded(true);
    }, (e: Error) => setLoadError(e.message));
  }, [code, meeting.id, merge]);

  useEffect(load, [load]);

  useEffect(() => {
    if (!loaded) return;
    let busy = false;
    const timer = setInterval(() => {
      if (busy || !since.current) return;
      busy = true;
      fetchState(code, meeting.id, minus(since.current, OVERLAP_MS)).then((state) => {
        merge(state.consensus, false);
        since.current = state.serverTs;
        setSyncError(false);
      }, () => setSyncError(true)).finally(() => (busy = false));
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [loaded, code, meeting.id, merge]);

  useEffect(() => {
    let cancelled = false;
    const get = () => fetchExperts(code, meeting.id).then((state) => {
      if (cancelled) return;
      const out: ExpertVerdicts = {};
      for (const [expert, rows] of Object.entries(state.verdicts)) {
        out[expert] = {};
        for (const [id, v] of Object.entries(rows)) out[expert][Number(id)] = v as Verdict;
      }
      setExperts(out);
    }, () => undefined);
    void get();
    const timer = setInterval(get, EXPERTS_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [code, meeting.id]);

  // --- derived --------------------------------------------------------------

  const verdicts = experts ?? {};
  const agreed = useCallback((id: number) => (experts ? agreedStep(meeting.experts, experts, id) : null),
    [experts, meeting.experts]);

  /** The meeting: its corridors in id order. The review: only the
   *  auto-classified ones, most doubtful first. */
  const mine = useMemo(() => {
    const ids = new Set(meeting.corridors);
    const all = index.filter((c) => ids.has(c.id));
    if (!review) return all;
    if (!experts) return [];
    return all.filter((c) => agreed(c.id) !== null)
      .map((c) => ({ c, d: doubtOf(meeting.experts, experts, c.id) }))
      .sort((a, b) => byDoubt(a.d, b.d) || a.c.id - b.c.id)
      .map(({ c }) => c);
  }, [index, meeting.corridors, meeting.experts, review, experts, agreed]);

  /** The review shows every corridor with its auto class, and sorts them
   *  into taken back or not. */
  const view = useCallback((id: number): View => {
    if (!review) return viewOf(stored[id], agreed(id));
    return { consensus: { ...(stored[id] ?? EMPTY_CONSENSUS), ...(agreed(id) ?? {}) }, auto: true };
  }, [review, stored, agreed]);
  const statusFor = useCallback((id: number): Status => {
    if (!review) return statusOf(stored[id], agreed(id));
    return stored[id]?.reopened ? "reopened" : "agreed";
  }, [review, stored, agreed]);
  /** The experts' width, standing in for the meeting's on an auto corridor. */
  const hintFor = useCallback((id: number) => (
    experts && !stored[id]?.sizeSet && (review || statusFor(id) === "agreed")
      ? sizeHint(meeting.experts, experts, id) : null
  ), [experts, stored, review, statusFor, meeting.experts]);

  const shown = useMemo(() => mine.filter((c) => {
    if (filters.region !== null && c.region !== filters.region) return false;
    const s = statusFor(c.id);
    if (review || filters.status === "all") return filters.status === "all" || s === filters.status;
    switch (filters.status) {
      // Gjenstår holds the overridden too: they are still to be discussed.
      case "todo": return s === "todo" || s === "reopened";
      // The two groups to go through one after the other: the ones that came
      // to the meeting from the start, and those the review took back - both
      // whether settled or not, so the list stays put while working through.
      case "original": return !agreed(c.id);
      case "reopened": return !!agreed(c.id) && !!stored[c.id]?.reopened;
      default: return s === filters.status;
    }
  }), [mine, filters, statusFor, review, agreed, stored]);

  /** What ← → walk through: the list, less the auto-classified corridors -
   *  nothing to discuss there. They stay in the list and open on a click;
   *  filtering to "Auto-klassifisert" walks only them. */
  const walk = useMemo(() => (review || filters.status === "agreed"
    ? shown : shown.filter((c) => statusFor(c.id) !== "agreed")), [review, shown, filters.status, statusFor]);

  const counts = useMemo(() => {
    const n = { agreed: 0, reopened: 0, settled: 0, todo: 0 };
    for (const c of mine) n[statusFor(c.id)] += 1;
    return n;
  }, [mine, statusFor]);

  // Where to start: where this meeting (or review) left off on this
  // machine, else the first corridor still to be settled (the review: the
  // most doubtful).
  useEffect(() => {
    if (currentId !== null || !mine.length || !loaded || !experts) return;
    const last = remembered<{ id: number | null }>(lastKey, { id: null }).id;
    const start = mine.find((c) => c.id === last)
      ?? (review ? undefined : mine.find((c) => ["todo", "reopened"].includes(statusFor(c.id)))) ?? mine[0];
    setCurrentId(start.id);
  }, [mine, loaded, experts, currentId, lastKey, statusFor, review]);

  const current = mine.find((c) => c.id === currentId) ?? null;
  const { consensus, auto } = view(currentId ?? -1);
  const currentAgreed = currentId === null ? null : agreed(currentId);
  const currentStatus = currentId === null ? null : statusFor(currentId);
  const reopened = currentId !== null && !!currentAgreed && !!stored[currentId]?.reopened;
  const badge = !currentAgreed ? null : reopened ? "reopened" as const
    : review || currentStatus === "agreed" ? "auto" as const : null;
  const position = currentId === null ? 0 : mine.findIndex((c) => c.id === currentId) + 1;

  useEffect(() => {
    if (currentId === null) return;
    for (const n of [stepFrom(walk, currentId, 1), stepFrom(walk, currentId, -1)]) {
      if (n !== null) prefetchCorridor(n);
    }
  }, [currentId]);

  useEffect(() => {
    remember(MAP_KEY, mapSettings);
  }, [mapSettings]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  // --- actions -------------------------------------------------------------

  const go = useCallback((id: number | null) => {
    if (id === null) return;
    queue.flush();
    setCurrentId(id);
    remember(lastKey, { id });
  }, [queue, lastKey]);

  const step = useCallback((dir: 1 | -1) => {
    if (currentId === null) return;
    const next = stepFrom(walk, currentId, dir);
    if (next === null) setToast(dir === 1 ? "Siste korridor å gå gjennom" : "Første korridor å gå gjennom");
    go(next);
  }, [walk, currentId, go]);

  /** A change to the current corridor, as it is. */
  const write = useCallback((patch: ConsensusPatch, delayMs = 0) => {
    if (currentId === null) return;
    setStored((prev) => ({ ...prev, [currentId]: { ...(prev[currentId] ?? EMPTY_CONSENSUS), ...patch } }));
    queue.push(meeting.id, currentId, patch, delayMs);
  }, [currentId, queue, meeting.id]);

  /** A change made in the meeting. On an auto-classified corridor the class
   *  goes along, so the stored row keeps it. */
  const update = useCallback((patch: ConsensusPatch, delayMs = 0) => {
    if (currentId === null) return;
    const { consensus: now, auto: isAuto } = view(currentId);
    write(isAuto && !("kast" in patch) ? { kast: now.kast, sub: now.sub, ...patch } : patch, delayMs);
  }, [currentId, view, write]);

  /** The review's one decision. Taken back, the corridor starts empty in
   *  the meeting; undone, it is auto-classified again. */
  const setReopened = (on: boolean) => write(on ? { reopened: true, kast: null, sub: 0 } : { reopened: false });

  /** The width in the review: stored as it is, without the class, so the
   *  corridor stays auto-classified. The same button again undoes it, and
   *  the experts' width (if any) stands in again. */
  const setReviewSize = (size: Step) => {
    const now = currentId === null ? undefined : stored[currentId];
    write(now?.sizeSet && now.size === size
      ? { size: 0, sizeSet: false, sizeReview: false }
      : { size, sizeSet: true, sizeReview: true });
  };

  const setMap = (patch: Partial<MapSettings>) => setMapSettings((m) => ({ ...m, ...patch }));

  const resetTest = async () => {
    if (!confirm("Slette alt som er lagret i prøvemøtet?")) return;
    try {
      const { removed } = await resetTestMeeting(code);
      setToast(`Slettet ${removed} korridorer`);
      load();
    } catch (e) {
      setToast((e as Error).message);
    }
  };

  // --- keyboard ------------------------------------------------------------

  const keyHandler = useRef<(e: KeyboardEvent) => void>(() => undefined);
  keyHandler.current = (e: KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const target = e.target as HTMLElement;
    if (target.closest("textarea, input, select")) {
      if (e.key === "Escape") target.blur();
      if (target instanceof HTMLTextAreaElement && !e.shiftKey) {
        const { selectionStart: from, selectionEnd: to, value } = target;
        const atEnd = from === to && to === value.length;
        const atStart = from === to && from === 0;
        if ((e.key === "ArrowRight" && atEnd) || (e.key === "ArrowLeft" && atStart)) {
          e.preventDefault();
          target.blur();
          step(e.key === "ArrowRight" ? 1 : -1);
        }
      }
      return;
    }
    if (helpOpen || model) {
      if (e.key === "Escape") {
        setHelpOpen(false);
        setModel(null);
      }
      return;
    }
    if (e.key === "Escape") return setListOpen(false);
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    const kast = KAST_KEYS[key];
    const actions: Record<string, () => void> = {
      ArrowRight: () => step(1),
      ArrowLeft: () => step(-1),
      " ": () => setMap({ tracks: !mapSettings.tracks }),
    };
    if (kast && !review) actions[key] = () => update({ kast: kast[0], sub: kast[1] });
    // The review's one decision (A is red − in the meeting).
    if (review && key === "a") actions.a = () => currentAgreed && setReopened(!reopened);
    const action = actions[key];
    if (action) {
      e.preventDefault();
      action();
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => keyHandler.current(e);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // --- render --------------------------------------------------------------

  if (loadError) {
    return (
      <div className="center-screen">
        <p>Kunne ikke hente møtet: {loadError}</p>
        <button className="primary-btn" onClick={load}>Prøv igjen</button>
      </div>
    );
  }

  const total = mine.length || 1;
  const pct = (n: number) => `${(100 * n) / total}%`;

  return (
    <div className="app">
      <MapView code={code} basemap={mapSettings.basemap} steepness={mapSettings.steepness} tracks={mapSettings.tracks}
               opacity={mapSettings.opacity} corridorId={current?.id ?? null} bbox={current?.bbox ?? null} />
      <ExpertsColumn experts={meeting.experts} verdicts={verdicts} corridorId={current?.id ?? null}
                     badge={badge} loading={!experts} />
      <aside className="sidebar">
        <header className="head">
          <div className="head-nav">
            <button className="tool-btn" title="Hurtigtaster" onClick={() => setHelpOpen(true)}><KeyboardIcon /></button>
            <button className="nav-btn" title="Forrige (←)" onClick={() => step(-1)}><ChevronLeft /></button>
            <div className="head-title">
              <div className="cid">{current?.id ?? "–"}</div>
              <div className="meta">{current?.region ?? " "}</div>
            </div>
            <button className="nav-btn" title="Neste (→)" onClick={() => step(1)}><ChevronRight /></button>
            <button className={`tool-btn ${listOpen ? "on" : ""}`} title="Korridorliste og filter"
                    onClick={() => setListOpen((o) => !o)}>{listOpen ? <CloseIcon /> : <ListIcon />}</button>
          </div>
          {review ? (
            <div className="meeting-progress">
              <div className="progress-bar three" aria-hidden="true">
                <div className="position" style={{ width: pct(position) }} />
              </div>
              <div className="progress-legend">
                <span>Nr. <b>{position || "–"}</b> av {mine.length}, mest tvilsomme først</span>
                <span><i className="reopened" />Auto-overstyring <b>{counts.reopened}</b></span>
              </div>
            </div>
          ) : (
            <div className="meeting-progress">
              <div className="progress-bar three" aria-hidden="true">
                <div className="agreed" style={{ width: pct(counts.agreed) }} />
                <div className="settled" style={{ width: pct(counts.settled) }} />
                <div className="reopened" style={{ width: pct(counts.reopened) }} />
              </div>
              <div className="progress-legend wrap">
                <span><i className="agreed" />Auto <b>{counts.agreed}</b></span>
                <span><i className="settled" />Avklart <b>{counts.settled}</b></span>
                <span><i />Gjenstår <b>{counts.todo + counts.reopened}</b></span>
                <span><i className="reopened" />herav auto-overstyring <b>{counts.reopened}</b></span>
              </div>
            </div>
          )}
        </header>

        {listOpen ? (
          <CorridorList all={mine} shown={shown} viewOf={view} statusOf={statusFor} currentId={currentId}
                        filters={filters} onFilters={setFilters} hintOf={hintFor} review={review}
                        onPick={(id) => { go(id); setListOpen(false); }} />
        ) : !loaded || !experts ? (
          <div className="empty">Henter …</div>
        ) : !mine.length ? (
          <div className="empty">{review ? "Ingen auto-klassifiserte korridorer." : "Møtet har ingen korridorer."}</div>
        ) : review ? (
          <div className="panels">
            <LayerPanel basemap={mapSettings.basemap} steepness={mapSettings.steepness}
                        tracks={mapSettings.tracks} opacity={mapSettings.opacity}
                        onBasemap={(basemap) => setMap({ basemap })}
                        onSteepness={(steepness) => setMap({ steepness })}
                        onTracks={(tracks) => setMap({ tracks })}
                        onOpacity={(opacity) => setMap({ opacity })} />
            {currentAgreed
              ? <>
                  <ReviewPanel agreed={currentAgreed} reopened={reopened} onReopen={setReopened} />
                  <SizePanel size={consensus.size} hint={hintFor(currentId ?? -1)} fromReview={consensus.sizeReview}
                             onSize={setReviewSize} />
                  {/* Stored as it is, without the class: the corridor stays auto-classified. */}
                  <FollowUpPanel consensus={consensus} onSet={(patch) => write(patch)}
                                 onText={(patch) => write(patch, TEXT_DELAY_MS)} onTextDone={() => queue.flush()} />
                </>
              : <div className="empty">Ikke lenger auto-klassifisert – en ekspert har endret vurderingen.</div>}
          </div>
        ) : (
          <div className="panels">
            <LayerPanel basemap={mapSettings.basemap} steepness={mapSettings.steepness}
                        tracks={mapSettings.tracks} opacity={mapSettings.opacity}
                        onBasemap={(basemap) => setMap({ basemap })}
                        onSteepness={(steepness) => setMap({ steepness })}
                        onTracks={(tracks) => setMap({ tracks })}
                        onOpacity={(opacity) => setMap({ opacity })} />
            <KastPanel consensus={consensus} auto={auto} onPick={(kast, sub) => update({ kast, sub })}
                       onClear={() => update({ kast: null, sub: 0 })} onShowModel={setModel}
                       reopenedFrom={reopened ? currentAgreed : null} />
            <SizePanel size={consensus.size} hint={hintFor(currentId ?? -1)} fromReview={consensus.sizeReview}
                       onSize={(size) => update({ size, sizeSet: true, sizeReview: false })} />
            <FollowUpPanel consensus={consensus} onSet={(patch) => update(patch)}
                           onText={(patch) => update(patch, TEXT_DELAY_MS)} onTextDone={() => queue.flush()} />
            <NotesPanel consensus={consensus}
                        onNote={(note) => update({ note }, TEXT_DELAY_MS)}
                        onTextDone={() => queue.flush()} />
          </div>
        )}

        <footer className="footer">
          <span className="who">
            <span className="meeting-name">{meeting.label}{review && " · gjennomgang"}</span>
            <button className="link" onClick={onLeave}>Bytt møte</button>
            {meeting.test && <button className="link" onClick={resetTest}>Nullstill</button>}
          </span>
          {syncError && status.kind === "saved"
            ? <span className="save warn" title="Ser ikke endringene til de andre akkurat nå"><i />Frakoblet – prøver igjen</span>
            : <SaveBadge status={status} />}
        </footer>
      </aside>
      {helpOpen && <ShortcutHelp review={review} onClose={() => setHelpOpen(false)} />}
      {model && <ModelImage model={model} onClose={() => setModel(null)} />}
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

function SaveBadge({ status }: { status: SaveStatus }) {
  switch (status.kind) {
    case "saved":
      return <span className="save ok"><i />Lagret</span>;
    case "saving":
      return <span className="save busy"><i />Lagrer …</span>;
    case "retrying":
      return <span className="save warn" title={status.message}><i />Ikke lagret ennå ({status.pending}) – prøver igjen</span>;
    case "unauthorized":
      return <span className="save bad"><i />Feil tilgangskode – {status.pending} venter</span>;
    case "error":
      return <span className="save bad" title={status.message}><i />{status.message}</span>;
  }
}

