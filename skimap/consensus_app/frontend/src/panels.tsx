import type { ReactNode } from "react";
import {
  CheckIcon, CloseIcon, EndpointIcon, MidpointIcon, MinusIcon, OtherIcon, PlusIcon, SplitIcon, TrashIcon,
} from "./icons";
import { hintLabel, hintSize, type Agreed, type SizeHint } from "./agreement";
import { KAST_MODELS, type KastModel } from "./kastModels";
import { BASEMAPS, STEEPNESS, TRACKS_THUMB, type BasemapId, type SteepnessId } from "./layers";
import {
  KAST_CLASSES, KAST_COLOUR, KAST_LABEL, SUB_MARK, type Consensus, type ConsensusPatch, type KastClass, type Step,
} from "./types";

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

// --- consensus class: the validation app's twelve steps ----------------------------

const SUB_LABEL: Record<Step, string> = { [-1]: "−", 0: "0", 1: "+" };

type KastProps = {
  consensus: Consensus;
  auto: boolean;
  onPick: (k: KastClass, s: Step) => void;
  onClear: () => void;
  onShowModel: (model: KastModel) => void;
  /** The auto class, when the review took the corridor back to discussion. */
  reopenedFrom?: Agreed | null;
};

/** As the validation app's KAST panel: four classes, each − 0 +. A pick
 *  shown from the experts' agreement is hatched until the meeting sets one. */
export function KastPanel({ consensus, auto, onPick, onClear, onShowModel, reopenedFrom }: KastProps) {
  const aside = (
    <span className="section-links">
      <button className="mini-btn" onClick={onClear} disabled={!consensus.kast || auto}
              style={{ visibility: consensus.kast && !auto ? "visible" : "hidden" }}>Nullstill</button>
    </span>
  );
  return (
    <Section title="Konsensus KAST-klasse" aside={aside}>
      <div className="kast-row">
        {KAST_CLASSES.map((k) => (
          <div key={k} className={`kast ${consensus.kast === k ? "chosen" : ""}`}
               style={{ ["--kast" as string]: KAST_COLOUR[k] }}>
            {([-1, 0, 1] as Step[]).map((s) => {
              const picked = consensus.kast === k && consensus.sub === s;
              return (
                <button key={s} className={`kast-seg ${picked ? "picked" : ""} ${picked && auto ? "auto" : ""}`}
                        title={`${KAST_LABEL[k]} ${SUB_LABEL[s]}`} aria-label={`${KAST_LABEL[k]} ${SUB_LABEL[s]}`}
                        aria-pressed={picked} onClick={() => onPick(k, s)}>
                  {SUB_LABEL[s]}
                </button>
              );
            })}
          </div>
        ))}
      </div>
      <div className="kast-extras">
        {auto
          ? <span className="auto-note"><CheckIcon size={14} /> Auto-klassifisert</span>
          : reopenedFrom
            ? <span className="auto-note reopened">Auto-overstyring</span>
            : <span />}
        <span className="model-links">
          {KAST_MODELS.map((m) => (
            <button key={m.id} className="mini-btn" onClick={() => onShowModel(m)}>{m.label}</button>
          ))}
        </span>
      </div>
      {reopenedFrom && (
        <p className="size-hint">
          Auto-klassifiseringen var {KAST_LABEL[reopenedFrom.kast].toLowerCase()}{SUB_MARK[reopenedFrom.sub] || " 0"}, overstyrt i gjennomgangen
        </p>
      )}
    </Section>
  );
}

// --- corridor size ---------------------------------------------------------

type SizeProps = {
  size: Step;
  onSize: (s: Step) => void;
  /** On an auto-classified corridor the meeting has not sized: the width
   *  the experts asked for, shown hatched and carried into the result as
   *  theirs, not the consensus's. */
  hint?: SizeHint | null;
  /** The width was chosen in the review of the auto-classification. */
  fromReview?: boolean;
};

export function SizePanel({ size, onSize, hint, fromReview = false }: SizeProps) {
  const hinted = (s: Step) => !!hint && (hintSize(hint) === s || (hintSize(hint) === null && s !== 0));
  const option = (s: Step, label: ReactNode) => {
    const picked = hint ? hinted(s) : size === s;
    return (
      <button className={`${picked ? "picked" : ""} ${picked && hint ? "auto" : ""}`} onClick={() => onSize(s)}>
        {label}
      </button>
    );
  };
  return (
    <Section title="Korridorbredde">
      <div className="segmented">
        {option(-1, <><MinusIcon /> Mindre</>)}
        {option(0, "OK")}
        {option(1, <><PlusIcon /> Større</>)}
      </div>
      {hint && <SizeHintNote hint={hint} />}
      {!hint && fromReview && <p className="size-hint">Satt i gjennomgangen av auto – ikke avklart i konsensus</p>}
    </Section>
  );
}

const SizeHintNote = ({ hint }: { hint: SizeHint }) => (
  <p className="size-hint">
    {hintLabel(hint)} fra {[...hint.smaller, ...hint.bigger].join(", ")} – ikke avklart i konsensus
  </p>
);

// --- the review of the auto-classification ----------------------------------

type ReviewProps = {
  agreed: Agreed;
  reopened: boolean;
  onReopen: (on: boolean) => void;
};

/** The auto class as a label, and the one thing to decide here: back to
 *  the meeting or not (also the A key). */
export function ReviewPanel({ agreed, reopened, onReopen }: ReviewProps) {
  return (
    <>
      <Section title="Auto-klassifisering">
        <div className="review-class">
          <span className="pill review-pill" style={{ ["--kast" as string]: KAST_COLOUR[agreed.kast] }}>
            {KAST_LABEL[agreed.kast]}{SUB_MARK[agreed.sub]}
          </span>
        </div>
      </Section>
      <button className={`reopen-btn ${reopened ? "on" : ""}`} aria-pressed={reopened} onClick={() => onReopen(!reopened)}>
        {reopened
          ? <><span className="reopen-main"><CheckIcon size={20} /> Tatt tilbake til diskusjon</span><span className="reopen-sub">Klikk eller A for å angre</span></>
          : <><span className="reopen-main">Ta tilbake til diskusjon</span><span className="reopen-sub">A · korridoren kommer da opp i møtet som auto-overstyring</span></>}
      </button>
    </>
  );
}

// --- what to do with the corridor later ------------------------------------

type FollowUpProps = {
  consensus: Consensus;
  /** A flag or a class: saved at once. */
  onSet: (patch: ConsensusPatch) => void;
  /** Text as it is typed: saved after a pause. */
  onText: (patch: ConsensusPatch) => void;
  onTextDone: () => void;
};

/** What to remember for later: three buttons, then Annet and Slett below;
 *  each but Slett opens its own fields. The fields stay while they hold
 *  anything, so switching a button off never hides what was written. */
export function FollowUpPanel({ consensus: c, onSet, onText, onTextDone }: FollowUpProps) {
  const showMid = c.midpoint || c.midpointWhere.trim() !== "";
  const showEnd = c.endpoint || c.endpointWhere.trim() !== "";
  const showOther = c.other || c.otherWhat.trim() !== "";
  const showSplit = c.split || [c.split1Where, c.split2Where].some((t) => t.trim()) || !!c.split1Kast || !!c.split2Kast;
  type Toggle = "midpoint" | "endpoint" | "split" | "other" | "remove";
  const toggle = (key: Toggle, on: boolean, icon: ReactNode, label: string) => (
    <button className={`todo-btn ${key} ${on ? "on" : ""}`} aria-pressed={on} onClick={() => onSet({ [key]: !on })}>
      {icon}<span>{label}</span>
    </button>
  );
  const where = (key: "midpointWhere" | "endpointWhere" | "otherWhat", placeholder: string) => (
    <textarea className="todo-text" value={c[key]} rows={2} maxLength={4000} placeholder={placeholder}
              onChange={(e) => onText({ [key]: e.target.value })} onBlur={onTextDone} />
  );
  const tour = (n: 1 | 2) => {
    const whereKey = n === 1 ? "split1Where" : "split2Where";
    const kastKey = n === 1 ? "split1Kast" : "split2Kast";
    const subKey = n === 1 ? "split1Sub" : "split2Sub";
    return (
      <div className="tour">
        <div className="tour-head">Tur {n}</div>
        <textarea className="todo-text" value={c[whereKey]} rows={1} maxLength={4000}
                  placeholder={`Hvor går tur ${n}?`}
                  onChange={(e) => onText({ [whereKey]: e.target.value })} onBlur={onTextDone} />
        <div className="kast-row small">
          {KAST_CLASSES.map((k) => (
            <div key={k} className={`kast ${c[kastKey] === k ? "chosen" : ""}`} style={{ ["--kast" as string]: KAST_COLOUR[k] }}>
              {([-1, 0, 1] as Step[]).map((s) => {
                const picked = c[kastKey] === k && c[subKey] === s;
                return (
                  <button key={s} className={`kast-seg ${picked ? "picked" : ""}`} aria-pressed={picked}
                          title={`Tur ${n}: ${KAST_LABEL[k]} ${SUB_LABEL[s]}`}
                          onClick={() => onSet(picked ? { [kastKey]: null, [subKey]: 0 } : { [kastKey]: k, [subKey]: s })}>
                    {SUB_LABEL[s]}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    );
  };
  return (
    <Section title="Videre arbeid">
      <div className="todo-btns">
        {toggle("midpoint", c.midpoint, <MidpointIcon />, "Legg til nytt mellompunkt")}
        {toggle("endpoint", c.endpoint, <EndpointIcon />, "Endre sluttpunkt")}
        {toggle("split", c.split, <SplitIcon />, "Til to turer")}
      </div>
      {showMid && where("midpointWhere", "Hvor skal det nye mellompunktet være?")}
      {showEnd && where("endpointWhere", "Hvor skal sluttpunktet være?")}
      {showSplit && <div className="tours">{tour(1)}{tour(2)}</div>}
      <div className="todo-btns two">
        {toggle("other", c.other, <OtherIcon />, "Annet")}
        {toggle("remove", c.remove, <TrashIcon />, "Slett")}
      </div>
      {showOther && where("otherWhat", "Hva annet skal gjøres?")}
    </Section>
  );
}

// --- the common comment ------------------------------------------------------

type NotesProps = {
  consensus: Consensus;
  onNote: (text: string) => void;
  onTextDone: () => void;
};

export function NotesPanel({ consensus, onNote, onTextDone }: NotesProps) {
  return (
    <Section title="Kommentar">
      <textarea className="common" value={consensus.note} rows={3} maxLength={4000}
                placeholder="Felles kommentar …"
                onChange={(e) => onNote(e.target.value)} onBlur={onTextDone} />
    </Section>
  );
}

// --- shortcuts -------------------------------------------------------------

const SHORTCUTS: [string, string][] = [
  ["← →", "Forrige / neste korridor (hopper over de auto-klassifiserte)"],
  ["1 2 3", "Grønn − / 0 / +"],
  ["Q W E", "Blå − / 0 / +"],
  ["A S D", "Rød − / 0 / +"],
  ["Z X C", "Svart − / 0 / +"],
  ["Space", "Vis / skjul spordata"],
];

const REVIEW_SHORTCUTS: [string, string][] = [
  ["← →", "Forrige / neste (mest tvilsomme først)"],
  ["A", "Ta tilbake til diskusjon / angre"],
  ["Space", "Vis / skjul spordata"],
];

export function ShortcutHelp({ onClose, review = false }: { onClose: () => void; review?: boolean }) {
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Hurtigtaster</h2>
        <dl className="shortcuts">
          {(review ? REVIEW_SHORTCUTS : SHORTCUTS).map(([k, what]) => (
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
