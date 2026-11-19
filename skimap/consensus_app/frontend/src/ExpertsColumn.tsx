import { useState, type ReactNode } from "react";
import { Avatar } from "./Avatar";
import type { ExpertVerdicts } from "./agreement";
import { CheckIcon, DoubtIcon, FlagIcon, MinusIcon, PlusIcon } from "./icons";
import { Section } from "./panels";
import {
  KAST_CLASSES, KAST_COLOUR, KAST_LABEL, SUB_MARK, type Expert, type Step, type Verdict,
} from "./types";

type Props = {
  experts: Expert[];
  verdicts: ExpertVerdicts;
  corridorId: number | null;
  /** The experts agree (see agreement.ts). */
  agreed: boolean;
  /** The experts' verdicts have not arrived yet. */
  loading: boolean;
};

type Mode = "compact" | "full";
const MODE_KEY = "konsensus.expertsView";

const readMode = (): Mode => {
  try {
    return localStorage.getItem(MODE_KEY) === "full" ? "full" : "compact";
  } catch {
    return "compact";
  }
};

/** The meeting's experts, one card each, top to bottom: what each of them
 *  said in the validation app. Read-only - the validation is not changed
 *  here. Two ways to show it, switched at the top and remembered per
 *  browser: compact (a label and the extras) or full (the validation app's
 *  own panel, scaled down so three fit). */
export function ExpertsColumn({ experts, verdicts, corridorId, agreed, loading }: Props) {
  const [mode, setMode] = useState<Mode>(readMode);
  const pick = (m: Mode) => {
    setMode(m);
    try {
      localStorage.setItem(MODE_KEY, m);
    } catch {
      // only a convenience
    }
  };
  return (
    <aside className={`experts ${mode}`}>
      <div className="experts-head">
        <div className="experts-title">
          <h2>Ekspertene</h2>
          <div className="mode-switch">
            <button className={mode === "compact" ? "on" : ""} onClick={() => pick("compact")}>Kompakt</button>
            <button className={mode === "full" ? "on" : ""} onClick={() => pick("full")}>Full</button>
          </div>
        </div>
        {!loading && corridorId !== null && agreed && <div className="agree"><CheckIcon size={15} /> Enige</div>}
      </div>
      <div className="expert-cards">
        {experts.map((e) => {
          const v = corridorId === null ? undefined : verdicts[e.id]?.[corridorId];
          return mode === "full"
            ? <FullCard key={e.id} expert={e} verdict={v} loading={loading} />
            : <CompactCard key={e.id} expert={e} verdict={v} loading={loading} />;
        })}
      </div>
    </aside>
  );
}

type CardProps = { expert: Expert; verdict: Verdict | undefined; loading: boolean };

function CompactCard({ expert: e, verdict: v, loading }: CardProps) {
  const note = v?.note.trim();
  return (
    <section className="expert">
      <header>
        <Avatar user={e} size={34} />
        <span className="expert-name">{e.name}</span>
        {loading
          ? <span className="pill todo">…</span>
          : v?.kast
            ? <span className="pill big" style={{ ["--kast" as string]: KAST_COLOUR[v.kast] }}>
                {KAST_LABEL[v.kast]}{SUB_MARK[v.sub]}
              </span>
            : <span className="pill todo">Ikke vurdert</span>}
      </header>
      {v?.kast && (v.size !== 0 || v.doubt || v.problematic) && (
        <div className="expert-tags">
          {v.size !== 0 && <span className="tag">{v.size < 0 ? "Mindre korridor" : "Større korridor"}</span>}
          {v.doubt && <span className="tag doubt"><DoubtIcon /> Usikker</span>}
          {v.problematic && <span className="tag problem"><FlagIcon /> Problematisk</span>}
        </div>
      )}
      {note
        ? <p className="expert-note">{note}</p>
        : v?.kast && <p className="expert-note none">Ingen notat</p>}
    </section>
  );
}

const STEP_LABEL: Record<Step, string> = { [-1]: "−", 0: "0", 1: "+" };

/** The validation app's KAST, Korridorbredde and Notater sections, as that
 *  expert left them: the same markup, scaled down so three fit the column
 *  without scrolling (Usikker sits by the name). Nothing clickable. */
function FullCard({ expert: e, verdict: v, loading }: CardProps) {
  const kast = v?.kast ?? null;
  const sub = v?.sub ?? 0;
  const size = v?.size ?? 0;
  const option = (s: Step, label: ReactNode) => (
    <button tabIndex={-1} className={kast && size === s ? "picked" : ""}>{label}</button>
  );
  return (
    <section className={`expert expert-full ${kast ? "" : "unjudged"}`}>
      <header>
        <Avatar user={e} size={28} />
        <span className="expert-name">{e.name}</span>
        {loading || !kast
          ? <span className="pill todo">{loading ? "…" : "Ikke vurdert"}</span>
          : <span className={`flag doubt ${v?.doubt ? "on" : ""}`}><DoubtIcon /> Usikker</span>}
      </header>
      <Section title="KAST-klasse">
        <div className="kast-row">
          {KAST_CLASSES.map((k) => (
            <div key={k} className={`kast ${kast === k ? "chosen" : ""}`} style={{ ["--kast" as string]: KAST_COLOUR[k] }}>
              {([-1, 0, 1] as Step[]).map((s) => (
                <button key={s} tabIndex={-1} className={`kast-seg ${kast === k && sub === s ? "picked" : ""}`}>
                  {STEP_LABEL[s]}
                </button>
              ))}
            </div>
          ))}
        </div>
      </Section>
      <Section title="Korridorbredde">
        <div className="segmented">
          {option(-1, <><MinusIcon /> Mindre</>)}
          {option(0, "OK")}
          {option(1, <><PlusIcon /> Større</>)}
        </div>
      </Section>
      <Section title="Notater">
        {/* Looks like the validation app's note box, but grows to fit the
            note instead of scrolling inside it. */}
        <div className={`note-box ${v?.note.trim() ? "" : "blank"}`}>{v?.note.trim() || "Ingen notat"}</div>
        <span className={`flag problem ${v?.problematic ? "on" : ""}`}><FlagIcon /> Problematisk for publisering</span>
      </Section>
    </section>
  );
}
