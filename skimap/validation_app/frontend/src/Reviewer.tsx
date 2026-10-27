import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchState, resetTestUser } from "./api";
import { CorridorList } from "./CorridorList";
import { prefetchCorridor } from "./data";
import { NO_FILTERS, applyFilters, stepFrom, verdictOf, type Filters } from "./filters";
import type { BasemapId, SteepnessId } from "./layers";
import { ChevronLeft, ChevronRight, CloseIcon, KeyboardIcon, ListIcon } from "./icons";
import { Avatar } from "./Avatar";
import { MapView } from "./MapView";
import type { KastModel } from "./kastModels";
import { KastPanel, LayerPanel, ModelImage, NotesPanel, ShortcutHelp, SizePanel } from "./panels";
import type { SaveQueue, SaveStatus } from "./saveQueue";
import {
  KAST_CLASSES, type CorridorInfo, type KastClass, type Step, type User,
  type Verdict, type VerdictPatch,
} from "./types";

type Props = {
  code: string;
  user: User;
  index: CorridorInfo[];
  queue: SaveQueue;
  status: SaveStatus;
  onSwitchUser: () => void;
};

type MapSettings = { basemap: BasemapId; steepness: SteepnessId | null; tracks: boolean; opacity: number };
// 0.3 is what the corridor review shows steepness at.
const DEFAULT_MAP: MapSettings = { basemap: "topo", steepness: "bratthet", tracks: false, opacity: 0.3 };
// Versioned: bumped when a default changes, or every browser that has
// opened the app keeps the old one.
const MAP_KEY = "validering.map.v2";

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

const NOTE_DELAY_MS = 800;

/** One keyboard row per class, top to bottom green to black, and left to
 *  right − 0 +. See ShortcutHelp in panels.tsx. */
const KAST_KEYS: Record<string, [KastClass, Step]> = Object.fromEntries(
  (["123", "qwe", "asd", "zxc"] as const).flatMap((row, i) =>
    [...row].map((key, j) => [key, [KAST_CLASSES[i], (j - 1) as Step]])),
);

export function Reviewer({ code, user, index, queue, status, onSwitchUser }: Props) {
  const [loadError, setLoadError] = useState<string | null>(null);
  const [assigned, setAssigned] = useState<number[] | null | undefined>(undefined);
  const [verdicts, setVerdicts] = useState<Record<number, Verdict>>({});
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [listOpen, setListOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [model, setModel] = useState<KastModel | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [mapSettings, setMapSettings] = useState<MapSettings>(() => remembered(MAP_KEY, DEFAULT_MAP));
  const lastKey = `validering.last.${user.id}`;

  // --- load ----------------------------------------------------------------

  const load = useCallback(() => {
    setLoadError(null);
    fetchState(code, user.id).then((state) => {
      const merged: Record<number, Verdict> = {};
      for (const [id, v] of Object.entries(state.verdicts)) merged[Number(id)] = v;
      // Changes still waiting in the queue are newer than what the server
      // has; show them, or the page would look like it forgot them.
      for (const op of queue.pending) {
        if (op.user === user.id) merged[op.corridor] = { ...verdictOf(merged, op.corridor), ...op.patch };
      }
      setVerdicts(merged);
      setAssigned(state.assigned);
    }, (e: Error) => setLoadError(e.message));
  }, [code, user.id, queue]);

  useEffect(load, [load]);

  const mine = useMemo(() => {
    if (assigned === undefined) return [];
    if (assigned === null) return index;
    const ids = new Set(assigned);
    return index.filter((c) => ids.has(c.id));
  }, [index, assigned]);

  const shown = useMemo(() => applyFilters(mine, verdicts, filters), [mine, verdicts, filters]);

  // Where to start: where this user left off, else the first not yet judged.
  useEffect(() => {
    if (currentId !== null || !mine.length) return;
    const last = remembered<{ id: number | null }>(lastKey, { id: null }).id;
    const start = mine.find((c) => c.id === last) ?? mine.find((c) => !verdicts[c.id]?.kast) ?? mine[0];
    setCurrentId(start.id);
  }, [mine, verdicts, currentId, lastKey]);

  const current = mine.find((c) => c.id === currentId) ?? null;
  const verdict = verdictOf(verdicts, currentId ?? -1);

  // The neighbours, so the next press of → draws at once. shown changes on
  // every verdict; the prefetch only needs a new corridor.
  useEffect(() => {
    if (currentId === null) return;
    for (const n of [stepFrom(shown, currentId, 1), stepFrom(shown, currentId, -1)]) {
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
    const next = stepFrom(shown, currentId, dir);
    if (next === null) setToast(dir === 1 ? "Siste korridor i listen" : "Første korridor i listen");
    go(next);
  }, [shown, currentId, go]);

  const update = useCallback((patch: VerdictPatch, delayMs = 0) => {
    if (currentId === null) return;
    setVerdicts((prev) => ({ ...prev, [currentId]: { ...verdictOf(prev, currentId), ...patch } }));
    queue.push(user.id, currentId, patch, delayMs);
  }, [currentId, queue, user.id]);

  const pickKast = (kast: KastClass, sub: Step) => update({ kast, sub });

  const setMap = (patch: Partial<MapSettings>) => setMapSettings((m) => ({ ...m, ...patch }));

  const resetTest = async () => {
    if (!confirm("Slette alle svarene til testbrukeren?")) return;
    try {
      const { removed } = await resetTestUser(code);
      setToast(`Slettet ${removed} svar`);
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
      // In the note the arrows move the caret - until it can go no further,
      // and then they move to the next or previous corridor as usual.
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
    // Nothing reaches the corridor behind an open overlay but its Esc.
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
    if (kast) actions[key] = () => pickKast(...kast);
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
        <p>Kunne ikke hente svarene dine: {loadError}</p>
        <button className="primary-btn" onClick={load}>Prøv igjen</button>
      </div>
    );
  }

  const reviewed = mine.filter((c) => verdicts[c.id]?.kast).length;

  return (
    <div className="app">
      <MapView code={code} basemap={mapSettings.basemap} steepness={mapSettings.steepness} tracks={mapSettings.tracks}
               opacity={mapSettings.opacity} corridorId={current?.id ?? null} bbox={current?.bbox ?? null}
/>
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
          <div className="progress" title={`${reviewed} av ${mine.length} vurdert`}>
            <div className="progress-bar"><div style={{ width: `${mine.length ? (100 * reviewed) / mine.length : 0}%` }} /></div>
            <span>{reviewed} / {mine.length} vurdert</span>
          </div>
        </header>

        {listOpen ? (
          <CorridorList all={mine} shown={shown} verdicts={verdicts} currentId={currentId}
                        filters={filters} onFilters={setFilters}
                        onPick={(id) => { go(id); setListOpen(false); }} />
        ) : assigned === undefined ? (
          <div className="empty">Henter …</div>
        ) : !mine.length ? (
          <div className="empty">Du har ingen korridorer tildelt ennå.</div>
        ) : (
          <div className="panels">
            <LayerPanel basemap={mapSettings.basemap} steepness={mapSettings.steepness}
                        tracks={mapSettings.tracks} opacity={mapSettings.opacity}
                        onBasemap={(basemap) => setMap({ basemap })}
                        onSteepness={(steepness) => setMap({ steepness })}
                        onTracks={(tracks) => setMap({ tracks })}
                        onOpacity={(opacity) => setMap({ opacity })} />
            <KastPanel verdict={verdict} onPick={pickKast} onClear={() => update({ kast: null, sub: 0 })}
                       onDoubt={(doubt) => update({ doubt })} onShowModel={setModel} />
            <SizePanel size={verdict.size} onSize={(size) => update({ size })} />
            <NotesPanel verdict={verdict}
                        onNote={(note) => update({ note }, NOTE_DELAY_MS)}
                        onNoteDone={() => queue.flush()}
                        onProblematic={(problematic) => update({ problematic })} />
          </div>
        )}

        <footer className="footer">
          <span className="who">
            <Avatar user={user} size={30} />
            {user.name}
            <button className="link" onClick={onSwitchUser}>Bytt</button>
            {user.id === "test" && <button className="link" onClick={resetTest}>Nullstill</button>}
          </span>
          <SaveBadge status={status} />
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
