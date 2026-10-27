import { Fragment, useMemo, useState } from "react";
import { num, pct, rupees } from "../format";
import type { Pick } from "../types";
import { PickDetail } from "./PickDetail";

type SortKey = "score" | "fundamental" | "technical" | "risk_pct" | "change_pct" | "symbol";

const COLS: { key: SortKey | null; label: string; num?: boolean }[] = [
  { key: null, label: "#" },
  { key: "symbol", label: "Stock" },
  { key: "score", label: "Score", num: true },
  { key: "change_pct", label: "Today", num: true },
  { key: null, label: "Entry", num: true },
  { key: null, label: "Stop", num: true },
  { key: null, label: "Target", num: true },
  { key: "risk_pct", label: "Risk", num: true },
  { key: null, label: "Qty", num: true },
  { key: null, label: "Position", num: true },
  { key: null, label: "Sector" },
];

function value(p: Pick, k: SortKey): number | string {
  if (k === "risk_pct") return p.plan.risk_pct;
  if (k === "symbol") return p.symbol;
  return p[k] ?? -Infinity;
}

export function ResultsTable({ picks, title }: { picks: Pick[]; title?: string }) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "score", desc: true });
  const [open, setOpen] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [breakoutsOnly, setBreakoutsOnly] = useState(false);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = picks.filter(
      (p) =>
        (!breakoutsOnly || p.breakout) &&
        (!q || p.symbol.toLowerCase().includes(q) || (p.company ?? "").toLowerCase().includes(q) || (p.sector ?? "").toLowerCase().includes(q)),
    );
    return [...filtered].sort((a, b) => {
      const va = value(a, sort.key);
      const vb = value(b, sort.key);
      const c = typeof va === "string" ? va.localeCompare(vb as string) : (va as number) - (vb as number);
      return sort.desc ? -c : c;
    });
  }, [picks, sort, query, breakoutsOnly]);

  return (
    <section className="card table-card">
      <div className="table-tools">
        {title && <h3>{title}</h3>}
        <input type="search" placeholder="Filter by stock or sector" value={query} onChange={(e) => setQuery(e.target.value)} />
        <label className="toggle">
          <input type="checkbox" checked={breakoutsOnly} onChange={(e) => setBreakoutsOnly(e.target.checked)} /> Breakouts only
        </label>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {COLS.map((c) => (
                <th
                  key={c.label}
                  className={`${c.num ? "num" : ""} ${c.key ? "sortable" : ""}`}
                  onClick={() => c.key && setSort((s) => ({ key: c.key!, desc: s.key === c.key ? !s.desc : c.key !== "symbol" }))}
                >
                  {c.label}
                  {c.key === sort.key ? (sort.desc ? " ▾" : " ▴") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <Fragment key={p.symbol}>
                <tr className={`row ${open === p.symbol ? "open" : ""}`} onClick={() => setOpen(open === p.symbol ? null : p.symbol)}>
                  <td className="muted">{i + 1}</td>
                  <td>
                    <div className="sym">
                      {p.symbol}
                      {p.breakout && <span className="badge" title="Breakout to a new high today">BO</span>}
                      {p.red_flags.length > 0 && <span className="flag" title={p.red_flags.join("; ")}>!</span>}
                    </div>
                    <small className="muted">{p.company}</small>
                  </td>
                  <td className="num">
                    <ScoreBar f={p.fundamental} t={p.technical} />
                  </td>
                  <td className={`num ${(p.change_pct ?? 0) >= 0 ? "up" : "down"}`}>{pct(p.change_pct)}</td>
                  <td className="num">{rupees(p.plan.entry)}</td>
                  <td className="num down">{rupees(p.plan.stop)}</td>
                  <td className="num up">{rupees(p.plan.target)}</td>
                  <td className="num">{p.plan.risk_pct.toFixed(1)}%</td>
                  <td className="num">{num(p.plan.shares)}</td>
                  <td className="num">{rupees(p.plan.position_value, 0)}</td>
                  <td className="muted">{p.sector}</td>
                </tr>
                {open === p.symbol && (
                  <tr className="detail-row">
                    <td colSpan={COLS.length}>
                      <PickDetail pick={p} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={COLS.length} className="empty">
                  No stocks match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ScoreBar({ f, t }: { f: number; t: number }) {
  return (
    <div className="score" title={`Fundamental ${f} / 50 · Technical ${t} / 50`}>
      <b>{(f + t).toFixed(1)}</b>
      <div className="bar">
        <span className="fund" style={{ width: `${f}%` }} />
        <span className="tech" style={{ width: `${t}%` }} />
      </div>
    </div>
  );
}
