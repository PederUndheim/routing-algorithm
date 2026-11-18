import { Avatar } from "./Avatar";
import type { ExpertVerdicts } from "./agreement";
import { CheckIcon, DoubtIcon, FlagIcon } from "./icons";
import { KAST_COLOUR, KAST_LABEL, SUB_MARK, type Expert } from "./types";

type Props = {
  experts: Expert[];
  verdicts: ExpertVerdicts;
  corridorId: number | null;
  /** Why they do not simply agree; empty when they do. */
  reasons: string[];
  /** The experts' verdicts have not arrived yet. */
  loading: boolean;
};

/** The meeting's experts, one card each, top to bottom: what each of them
 *  said in the validation app. Read-only - the validation is not changed
 *  here. */
export function ExpertsColumn({ experts, verdicts, corridorId, reasons, loading }: Props) {
  return (
    <aside className="experts">
      <div className="experts-head">
        <h2>Ekspertene</h2>
        {!loading && corridorId !== null && (
          reasons.length
            ? <ul className="reasons">{reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            : <div className="agree"><CheckIcon size={15} /> Enige</div>
        )}
      </div>
      <div className="expert-cards">
        {experts.map((e) => {
          const v = corridorId === null ? undefined : verdicts[e.id]?.[corridorId];
          const note = v?.note.trim();
          return (
            <section key={e.id} className="expert">
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
        })}
      </div>
    </aside>
  );
}
