import { useEffect, useRef } from "react";
import { NO_FILTERS, isFiltered, type Filters, type Status, type View } from "./agreement";
import { KAST_COLOUR, KAST_LABEL, SUB_MARK, type CorridorInfo } from "./types";

type Props = {
  all: CorridorInfo[];
  shown: CorridorInfo[];
  viewOf: (id: number) => View;
  statusOf: (id: number) => Status;
  currentId: number | null;
  filters: Filters;
  onFilters: (f: Filters) => void;
  onPick: (id: number) => void;
};

const STATUS: [Filters["status"], string][] = [
  ["all", "Alle"], ["todo", "Gjenstår"], ["settled", "Avklart i møtet"], ["agreed", "Enige fra start"],
];

export function CorridorList({ all, shown, viewOf, statusOf, currentId, filters, onFilters, onPick }: Props) {
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
          {STATUS.map(([v, label]) => (
            <button key={v} className={filters.status === v ? "on" : ""} onClick={() => set({ status: v })}>
              {label}
            </button>
          ))}
        </div>
        <div className="seg">
          <button className={filters.problematic ? "on" : ""}
                  onClick={() => set({ problematic: !filters.problematic })}>Problematisk</button>
        </div>
        <div className="list-count">
          <span>Viser {shown.length} av {all.length}</span>
          {isFiltered(filters) && <button className="link" onClick={() => onFilters(NO_FILTERS)}>Nullstill filter</button>}
        </div>
      </div>
      <div className="rows">
        {shown.map((c) => {
          const { consensus: v } = viewOf(c.id);
          const status = statusOf(c.id);
          const note = [v.change.trim(), v.note.trim()].filter(Boolean).join(" · ");
          return (
            <button key={c.id} ref={c.id === currentId ? current : undefined}
                    className={`row ${c.id === currentId ? "current" : ""} ${status}`} onClick={() => onPick(c.id)}>
              <span className="row-id">{c.id}</span>
              <span className="row-body">
                <span className="row-top">
                  <span className="row-region">{c.region}</span>
                  {v.kast
                    ? <span className="pill" style={{ ["--kast" as string]: KAST_COLOUR[v.kast] }}>{KAST_LABEL[v.kast]}{SUB_MARK[v.sub]}</span>
                    : <span className="pill todo">Gjenstår</span>}
                </span>
                {(status === "agreed" || v.problematic || v.size !== 0 || v.midpoint || v.endpoint || v.split || note) && (
                  <span className="row-tags">
                    {status === "agreed" && <span className="tag agreed">Enige fra start</span>}
                    {v.problematic && <span className="tag problem">Problematisk</span>}
                    {v.size !== 0 && <span className="tag">{v.size < 0 ? "Mindre korridor" : "Større korridor"}</span>}
                    {v.midpoint && <span className="tag todo">Nytt mellompunkt</span>}
                    {v.endpoint && <span className="tag todo">Endre sluttpunkt</span>}
                    {v.split && <span className="tag todo">To turer</span>}
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
