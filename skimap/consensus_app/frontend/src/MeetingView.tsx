import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchExperts, fetchState, resetTestMeeting } from "./api";
import {
  NO_FILTERS, agreedStep, disagreements, statusOf, stepFrom, viewOf,
  type ExpertVerdicts, type Filters,
} from "./agreement";
import { CorridorList } from "./CorridorList";
import { prefetchCorridor } from "./data";
import { ExpertsColumn } from "./ExpertsColumn";
import { ChevronLeft, ChevronRight, CloseIcon, KeyboardIcon, ListIcon } from "./icons";
import type { KastModel } from "./kastModels";
import type { BasemapId, SteepnessId } from "./layers";
import { MapView } from "./MapView";
import { FollowUpPanel, KastPanel, LayerPanel, ModelImage, NotesPanel, ShortcutHelp, SizePanel } from "./panels";
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

export function MeetingView({ code, meeting, index, queue, status, onLeave }: Props) {
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
  const lastKey = `konsensus.last.${meeting.id}`;
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

  const mine = useMemo(() => {
    const ids = new Set(meeting.corridors);
    return index.filter((c) => ids.has(c.id));
  }, [index, meeting.corridors]);

  const verdicts = experts ?? {};
  const agreed = useCallback((id: number) => (experts ? agreedStep(meeting.experts, experts, id) : null),
    [experts, meeting.experts]);
  const view = useCallback((id: number) => viewOf(stored[id], agreed(id)), [stored, agreed]);
  const statusFor = useCallback((id: number) => statusOf(stored[id], agreed(id)), [stored, agreed]);

  const shown = useMemo(() => mine.filter((c) => {
    if (filters.region !== null && c.region !== filters.region) return false;
    if (filters.status !== "all" && statusFor(c.id) !== filters.status) return false;
    if (filters.problematic && !view(c.id).consensus.problematic) return false;
    return true;
  }), [mine, filters, statusFor, view]);

  /** What ← → walk through: the list, less the corridors the experts agreed
   *  on - nothing to discuss there. They stay in the list and open on a
   *  click; filtering to "Enige fra start" walks only them. */
  const walk = useMemo(() => (filters.status === "agreed"
    ? shown : shown.filter((c) => statusFor(c.id) !== "agreed")), [shown, filters.status, statusFor]);

  const counts = useMemo(() => {
    const n = { agreed: 0, settled: 0, todo: 0 };
    for (const c of mine) n[statusFor(c.id)] += 1;
    return n;
  }, [mine, statusFor]);

  // Where to start: where this meeting left off on this machine, else the
  // first corridor still to be settled.
  useEffect(() => {
    if (currentId !== null || !mine.length || !loaded || !experts) return;
    const last = remembered<{ id: number | null }>(lastKey, { id: null }).id;
    const start = mine.find((c) => c.id === last) ?? mine.find((c) => statusFor(c.id) === "todo") ?? mine[0];
    setCurrentId(start.id);
  }, [mine, loaded, experts, currentId, lastKey, statusFor]);

  const current = mine.find((c) => c.id === currentId) ?? null;
  const { consensus, auto } = view(currentId ?? -1);
  const expertsAgree = currentId !== null && !!experts && !disagreements(meeting.experts, experts, currentId).length;

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

  /** A change to the current corridor. On one shown from the experts'
   *  agreement, the class goes along, so the stored row keeps it. */
  const update = useCallback((patch: ConsensusPatch, delayMs = 0) => {
    if (currentId === null) return;
    const { consensus: now, auto: isAuto } = view(currentId);
    const full = isAuto && !("kast" in patch) ? { kast: now.kast, sub: now.sub, ...patch } : patch;
    setStored((prev) => ({ ...prev, [currentId]: { ...(prev[currentId] ?? EMPTY_CONSENSUS), ...full } }));
    queue.push(meeting.id, currentId, full, delayMs);
  }, [currentId, view, queue, meeting.id]);

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
    if (kast) actions[key] = () => update({ kast: kast[0], sub: kast[1] });
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
                     agreed={expertsAgree} loading={!experts} />
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
          <div className="meeting-progress">
            <div className="progress-bar three" aria-hidden="true">
              <div className="agreed" style={{ width: pct(counts.agreed) }} />
              <div className="settled" style={{ width: pct(counts.settled) }} />
            </div>
            <div className="progress-legend">
              <span><i className="agreed" />Enige fra start <b>{counts.agreed}</b></span>
              <span><i className="settled" />Avklart i møtet <b>{counts.settled}</b></span>
              <span><i />Gjenstår <b>{counts.todo}</b></span>
            </div>
          </div>
        </header>

        {listOpen ? (
          <CorridorList all={mine} shown={shown} viewOf={view} statusOf={statusFor} currentId={currentId}
                        filters={filters} onFilters={setFilters}
                        onPick={(id) => { go(id); setListOpen(false); }} />
        ) : !loaded || !experts ? (
          <div className="empty">Henter …</div>
        ) : !mine.length ? (
          <div className="empty">Møtet har ingen korridorer.</div>
        ) : (
          <div className="panels">
            <LayerPanel basemap={mapSettings.basemap} steepness={mapSettings.steepness}
                        tracks={mapSettings.tracks} opacity={mapSettings.opacity}
                        onBasemap={(basemap) => setMap({ basemap })}
                        onSteepness={(steepness) => setMap({ steepness })}
                        onTracks={(tracks) => setMap({ tracks })}
                        onOpacity={(opacity) => setMap({ opacity })} />
            <KastPanel consensus={consensus} auto={auto} onPick={(kast, sub) => update({ kast, sub })}
                       onClear={() => update({ kast: null, sub: 0 })} onShowModel={setModel} />
            <SizePanel size={consensus.size} onSize={(size) => update({ size })} />
            <FollowUpPanel consensus={consensus} onSet={(patch) => update(patch)}
                           onText={(patch) => update(patch, TEXT_DELAY_MS)} onTextDone={() => queue.flush()} />
            <NotesPanel consensus={consensus}
                        onProblematic={(problematic) => update({ problematic })}
                        onChange={(change) => update({ change }, TEXT_DELAY_MS)}
                        onNote={(note) => update({ note }, TEXT_DELAY_MS)}
                        onTextDone={() => queue.flush()} />
          </div>
        )}

        <footer className="footer">
          <span className="who">
            <span className="meeting-name">{meeting.label}</span>
            <button className="link" onClick={onLeave}>Bytt møte</button>
            {meeting.test && <button className="link" onClick={resetTest}>Nullstill</button>}
          </span>
          {syncError && status.kind === "saved"
            ? <span className="save warn" title="Ser ikke endringene til de andre akkurat nå"><i />Frakoblet – prøver igjen</span>
            : <SaveBadge status={status} />}
        </footer>
      </aside>
      {helpOpen && <ShortcutHelp onClose={() => setHelpOpen(false)} />}
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

