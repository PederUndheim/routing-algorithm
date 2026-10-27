import type { ReactNode } from "react";
import { CloseIcon, DoubtIcon, FlagIcon, MinusIcon, PlusIcon } from "./icons";
import { KAST_MODELS, type KastModel } from "./kastModels";
import { BASEMAPS, STEEPNESS, TRACKS_THUMB, type BasemapId, type SteepnessId } from "./layers";
import { KAST_CLASSES, KAST_COLOUR, KAST_LABEL, type KastClass, type Step, type Verdict } from "./types";

export const Section = ({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) => (
  <section className="section">
    <div className="section-head">
      <h2>{title}</h2>
      {aside}
    </div>
    {children}
  </section>
);

// --- map layers -------------------------------------------------------------

const LayerCard = ({ label, thumb, on, onClick }: {
  label: string; thumb: string; on: boolean; onClick: () => void;
}) => (
  <button className={`layer ${on ? "on" : ""}`} onClick={onClick} aria-pressed={on}
          style={{ backgroundImage: `url(${thumb})` }}>
    <span className="layer-label">{label}</span>
  </button>
);

type LayerProps = {
  basemap: BasemapId;
  steepness: SteepnessId | null;
  tracks: boolean;
  opacity: number;
  onBasemap: (b: BasemapId) => void;
  onSteepness: (s: SteepnessId | null) => void;
  onTracks: (on: boolean) => void;
  onOpacity: (o: number) => void;
};

export function LayerPanel(p: LayerProps) {
  const steep = (id: SteepnessId) => (
    <LayerCard label={STEEPNESS[id].label} thumb={STEEPNESS[id].thumb} on={p.steepness === id}
               onClick={() => p.onSteepness(p.steepness === id ? null : id)} />
  );
  return (
    <Section title="Kart">
      <div className="layer-row">
        {(Object.keys(BASEMAPS) as BasemapId[]).map((id) => (
          <LayerCard key={id} label={BASEMAPS[id].label} thumb={BASEMAPS[id].thumb}
                     on={p.basemap === id} onClick={() => p.onBasemap(id)} />
        ))}
      </div>
      <div className="layer-row">
        {steep("bratthet")}
        {steep("bratthet_utlop")}
        <LayerCard label="Spordata" thumb={TRACKS_THUMB} on={p.tracks} onClick={() => p.onTracks(!p.tracks)} />
      </div>
      <label className="slider">
        <span>Bratthet</span>
        {/* Let go and focus goes back to the page, or ← → would keep moving
            the slider instead of stepping corridors. */}
        <input type="range" min={0.1} max={1} step={0.05} value={p.opacity}
               onChange={(e) => p.onOpacity(Number(e.target.value))}
               onPointerUp={(e) => e.currentTarget.blur()} />
        <span className="slider-value">{Math.round(p.opacity * 100)} %</span>
      </label>
    </Section>
  );
}

// --- KAST -----------------------------------------------------------------

const SUB_LABEL: Record<Step, string> = { [-1]: "−", 0: "0", 1: "+" };

type KastProps = {
  verdict: Verdict;
  onPick: (k: KastClass, s: Step) => void;
  onClear: () => void;
  onDoubt: (on: boolean) => void;
  onShowModel: (model: KastModel) => void;
};

export function KastPanel({ verdict, onPick, onClear, onDoubt, onShowModel }: KastProps) {
  const aside = (
    <span className="section-links">
      {/* Always there, hidden while there is nothing to clear, so setting a
          class does not nudge the layout. */}
      <button className="mini-btn" onClick={onClear} disabled={!verdict.kast}
              style={{ visibility: verdict.kast ? "visible" : "hidden" }}>Nullstill</button>
    </span>
  );
  return (
    <Section title="KAST-klasse" aside={aside}>
      <div className="kast-row">
        {KAST_CLASSES.map((k) => (
          <div key={k} className={`kast ${verdict.kast === k ? "chosen" : ""}`}
               style={{ ["--kast" as string]: KAST_COLOUR[k] }}>
            {([-1, 0, 1] as Step[]).map((s) => (
              <button key={s} className={`kast-seg ${verdict.kast === k && verdict.sub === s ? "picked" : ""}`}
                      title={`${KAST_LABEL[k]} ${SUB_LABEL[s]}`} aria-label={`${KAST_LABEL[k]} ${SUB_LABEL[s]}`}
                      onClick={() => onPick(k, s)}>
                {SUB_LABEL[s]}
              </button>
            ))}
          </div>
        ))}
      </div>
      <div className="kast-extras">
        <button className={`flag doubt ${verdict.doubt ? "on" : ""}`} aria-pressed={verdict.doubt}
                onClick={() => onDoubt(!verdict.doubt)}>
          <DoubtIcon /> Usikker
        </button>
        <span className="model-links">
          {KAST_MODELS.map((m) => (
            <button key={m.id} className="mini-btn" onClick={() => onShowModel(m)}>{m.label}</button>
          ))}
        </span>
      </div>
    </Section>
  );
}

// --- corridor size ---------------------------------------------------------

export function SizePanel({ size, onSize }: { size: Step; onSize: (s: Step) => void }) {
  const option = (s: Step, label: ReactNode) => (
    <button className={size === s ? "picked" : ""} onClick={() => onSize(s)}>{label}</button>
  );
  return (
    <Section title="Korridorbredde">
      <div className="segmented">
        {option(-1, <><MinusIcon /> Mindre</>)}
        {option(0, "OK")}
        {option(1, <><PlusIcon /> Større</>)}
      </div>
    </Section>
  );
}

// --- notes ---------------------------------------------------------------

type NotesProps = {
  verdict: Verdict;
  onNote: (note: string) => void;
  onNoteDone: () => void;
  onProblematic: (on: boolean) => void;
};

export function NotesPanel({ verdict, onNote, onNoteDone, onProblematic }: NotesProps) {
  return (
    <Section title="Notater">
      <textarea value={verdict.note} rows={2} maxLength={4000}
                placeholder="Kommentar til korridoren …"
                onChange={(e) => onNote(e.target.value)} onBlur={onNoteDone} />
      <button className={`flag problem ${verdict.problematic ? "on" : ""}`} aria-pressed={verdict.problematic}
              onClick={() => onProblematic(!verdict.problematic)}>
        <FlagIcon /> Problematisk for publisering
      </button>
    </Section>
  );
}

// --- shortcuts -------------------------------------------------------------

const SHORTCUTS: [string, string][] = [
  ["← →", "Forrige / neste korridor"],
  ["1 2 3", "Grønn − / 0 / +"],
  ["Q W E", "Blå − / 0 / +"],
  ["A S D", "Rød − / 0 / +"],
  ["Z X C", "Svart − / 0 / +"],
  ["Space", "Vis / skjul spordata"],
];

export function ShortcutHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Hurtigtaster</h2>
        <dl className="shortcuts">
          {SHORTCUTS.map(([k, what]) => (
            <div key={k}>
              <dt>{k.split(" ").map((part) => <kbd key={part}>{part}</kbd>)}</dt>
              <dd>{what}</dd>
            </div>
          ))}
        </dl>
        <button className="primary-btn" onClick={onClose}>Lukk</button>
      </div>
    </div>
  );
}

// --- KAST models -------------------------------------------------------------

export function ModelImage({ model, onClose }: { model: KastModel; onClose: () => void }) {
  return (
    <div className="modal-back" onClick={onClose}>
      <figure className="model-modal" onClick={(e) => e.stopPropagation()}>
        <figcaption>
          <h2>KAST – {model.label.toLowerCase()}</h2>
          <button className="tool-btn" title="Lukk (Esc)" onClick={onClose}><CloseIcon /></button>
        </figcaption>
        <img src={model.image} alt={`KAST ${model.label}`} />
      </figure>
    </div>
  );
}
