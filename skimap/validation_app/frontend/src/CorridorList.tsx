import { useEffect, useRef } from "react";
import { NO_FILTERS, isFiltered, verdictOf, type Filters } from "./filters";
import { KAST_CLASSES, KAST_COLOUR, KAST_LABEL, type CorridorInfo, type Verdict } from "./types";

type Props = {
  all: CorridorInfo[];
  shown: CorridorInfo[];
  verdicts: Record<number, Verdict>;
  currentId: number | null;
  filters: Filters;
  onFilters: (f: Filters) => void;
  onPick: (id: number) => void;
};

const SUB = { [-1]: " −", 0: "", 1: " +" } as const;

export function CorridorList({ all, shown, verdicts, currentId, filters, onFilters, onPick }: Props) {
  const regions = [...new Set(all.map((c) => c.region))];
  const set = (patch: Partial<Filters>) => onFilters({ ...filters, ...patch });
  const current = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    current.current?.scrollIntoView({ block: "center" });
  }, []);

  return (
    <div className="list-panel">
      <div className="filters">
        <select value={filters.region ?? ""} onChange={(e) => set({ region: e.target.value || null })}>
          <option value="">Alle regioner</option>
          {regions.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <div className="seg">
          {([["all", "Alle"], ["todo", "Ikke vurdert"], ["done", "Vurdert"]] as const).map(([v, label]) => (
            <button key={v} className={filters.status === v ? "on" : ""} onClick={() => set({ status: v })}>
              {label}
            </button>
          ))}
        </div>
        <div className="seg">
          <button className={filters.kast === null ? "on" : ""} onClick={() => set({ kast: null })}>Alle</button>
          {KAST_CLASSES.map((k) => (
            <button key={k} className={filters.kast === k ? "on" : ""} onClick={() => set({ kast: k })}>
              <span className="swatch" style={{ background: KAST_COLOUR[k] }} />{KAST_LABEL[k]}
            </button>
          ))}
        </div>
        <div className="seg">
          <button className={filters.doubt ? "on" : ""} onClick={() => set({ doubt: !filters.doubt })}>Usikker</button>
          <button className={filters.problematic ? "on" : ""}
                  onClick={() => set({ problematic: !filters.problematic })}>Problematisk</button>
          <button className={filters.note ? "on" : ""} onClick={() => set({ note: !filters.note })}>Har notat</button>
        </div>
        <div className="list-count">
          <span>Viser {shown.length} av {all.length}</span>
          {isFiltered(filters) && <button className="link" onClick={() => onFilters(NO_FILTERS)}>Nullstill filter</button>}
        </div>
      </div>
      <div className="rows">
        {shown.map((c) => {
          const v = verdictOf(verdicts, c.id);
          const note = v.note.trim();
          return (
            <button key={c.id} ref={c.id === currentId ? current : undefined}
                    className={`row ${c.id === currentId ? "current" : ""}`} onClick={() => onPick(c.id)}>
              <span className="row-id">{c.id}</span>
              <span className="row-body">
                <span className="row-top">
                  <span className="row-region">{c.region}</span>
                  {v.kast
                    ? <span className="pill" style={{ ["--kast" as string]: KAST_COLOUR[v.kast] }}>
                        {KAST_LABEL[v.kast]}{SUB[v.sub]}
                      </span>
                    : <span className="pill todo">Ikke vurdert</span>}
                </span>
                {(v.doubt || v.problematic || v.size !== 0 || note) && (
                  <span className="row-tags">
                    {v.doubt && <span className="tag doubt">Usikker</span>}
                    {v.problematic && <span className="tag problem">Problematisk</span>}
                    {v.size !== 0 && <span className="tag">{v.size < 0 ? "Mindre korridor" : "Større korridor"}</span>}
                    {note && <span className="row-note">{note}</span>}
                  </span>
                )}
              </span>
            </button>
          );
        })}
        {!shown.length && <div className="empty">Ingen korridorer passer filteret.</div>}
      </div>
    </div>
  );
}
