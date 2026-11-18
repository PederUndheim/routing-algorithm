import type { ReactNode } from "react";
import { CheckIcon, CloseIcon, FlagIcon, MinusIcon, PlusIcon } from "./icons";
import { KAST_MODELS, type KastModel } from "./kastModels";
import { BASEMAPS, STEEPNESS, TRACKS_THUMB, type BasemapId, type SteepnessId } from "./layers";
import { KAST_CLASSES, KAST_COLOUR, KAST_LABEL, type Consensus, type KastClass, type Step } from "./types";

export const Section = ({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) => (
  <section className="section">
    <div className="section-head">
      <h2>{title}</h2>
      {aside}
    </div>
    {children}
  </section>
);

// --- map layers (as in the validation app) -----------------------------------

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
        <input type="range" min={0.1} max={1} step={0.05} value={p.opacity}
               onChange={(e) => p.onOpacity(Number(e.target.value))}
               onPointerUp={(e) => e.currentTarget.blur()} />
        <span className="slider-value">{Math.round(p.opacity * 100)} %</span>
      </label>
    </Section>
  );
}

// --- consensus class: main classes only ------------------------------------------

type KastProps = {
  consensus: Consensus;
  auto: boolean;
  onPick: (k: KastClass) => void;
  onClear: () => void;
  onShowModel: (model: KastModel) => void;
};

export function KastPanel({ consensus, auto, onPick, onClear, onShowModel }: KastProps) {
  const aside = (
    <span className="section-links">
      <button className="mini-btn" onClick={onClear} disabled={!consensus.kast || auto}
              style={{ visibility: consensus.kast && !auto ? "visible" : "hidden" }}>Nullstill</button>
    </span>
  );
  return (
    <Section title="Konsensus KAST-klasse" aside={aside}>
      <div className="kast-row">
        {KAST_CLASSES.map((k, i) => (
          <button key={k} className={`kast-main ${consensus.kast === k ? "picked" : ""} ${auto ? "auto" : ""}`}
                  style={{ ["--kast" as string]: KAST_COLOUR[k] }} title={`${KAST_LABEL[k]} (${i + 1})`}
                  aria-pressed={consensus.kast === k} onClick={() => onPick(k)}>
            {KAST_LABEL[k]}
          </button>
        ))}
      </div>
      <div className="kast-extras">
        {auto
          ? <span className="auto-note"><CheckIcon size={14} /> Enige fra start</span>
          : <span />}
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

// --- publishing and the common comment ---------------------------------------------

type NotesProps = {
  consensus: Consensus;
  onProblematic: (on: boolean) => void;
  onChange: (text: string) => void;
  onNote: (text: string) => void;
  onTextDone: () => void;
};

export function NotesPanel({ consensus, onProblematic, onChange, onNote, onTextDone }: NotesProps) {
  // The "what to change" box belongs to the flag, so it shows with it - and
  // stays while it holds text, so un-ticking the flag never hides words.
  const showChange = consensus.problematic || consensus.change.trim() !== "";
  return (
    <Section title="Publisering og kommentar">
      <button className={`flag problem ${consensus.problematic ? "on" : ""}`} aria-pressed={consensus.problematic}
              onClick={() => onProblematic(!consensus.problematic)}>
        <FlagIcon /> Problematisk for publisering
      </button>
      {showChange && (
        <textarea className="change" value={consensus.change} rows={2} maxLength={4000}
                  placeholder="Hva bør endres før publisering?"
                  onChange={(e) => onChange(e.target.value)} onBlur={onTextDone} />
      )}
      <textarea className="common" value={consensus.note} rows={3} maxLength={4000}
                placeholder="Felles kommentar …"
                onChange={(e) => onNote(e.target.value)} onBlur={onTextDone} />
    </Section>
  );
}

// --- shortcuts -------------------------------------------------------------

const SHORTCUTS: [string, string][] = [
  ["← →", "Forrige / neste korridor"],
  ["1 2 3 4", "Grønn / blå / rød / svart"],
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
