import { num, pct } from "../format";
import type { ScanResult } from "../types";

const LABELS: Record<string, string> = {
  "NSE:CNX500": "Nifty 500",
  "NSE:NIFTY": "Nifty 50",
};

export function Regime({ result }: { result: ScanResult }) {
  const r = result.regime;
  return (
    <section className={`regime card ${r.status}`}>
      <div className="regime-head">
        <strong>Market: {r.status.replace("-", " ")}</strong>
        <span>{r.note}</span>
      </div>
      <div className="indices">
        {Object.entries(r.indices).map(([t, q]) =>
          q.close ? (
            <div key={t} className="index">
              <b>{LABELS[t] ?? t}</b> {num(q.close, 2)} <span className={(q.change ?? 0) >= 0 ? "up" : "down"}>{pct(q.change, 2)}</span>
              <small>
                50-DMA {q.sma50 ? num(q.sma50) : "–"} · 200-DMA {q.sma200 ? num(q.sma200) : "–"}
                {q.rsi ? ` · RSI ${q.rsi.toFixed(0)}` : ""}
              </small>
            </div>
          ) : null,
        )}
      </div>
    </section>
  );
}

export function Stats({ result }: { result: ScanResult }) {
  const top = result.sectors[0];
  const concentrated = top && result.total_picks >= 4 && top.count / result.total_picks >= 0.3;
  const dropped = Object.entries(result.dropped).sort((a, b) => b[1] - a[1]);
  return (
    <section className="stats">
      <div className="funnel">
        <Stat label="Fetched" value={result.fetched} />
        <Stat label={`In ${result.universe_label}`} value={result.in_universe} />
        <Stat label="Passed filters" value={result.passed_filters} />
        <Stat label={`Picks (score ≥ ${result.cutoff})`} value={result.total_picks} accent />
      </div>
      {dropped.length > 0 && (
        <p className="chips">
          <span className="muted">Dropped:</span>
          {dropped.map(([k, v]) => (
            <span key={k} className="chip">
              {k} <b>{v}</b>
            </span>
          ))}
        </p>
      )}
      {result.sectors.length > 0 && (
        <p className="chips">
          <span className="muted">Sectors:</span>
          {result.sectors.map((s) => (
            <span key={s.sector} className="chip">
              {s.sector} <b>{s.count}</b>
            </span>
          ))}
        </p>
      )}
      {concentrated && (
        <p className="warn">
          {top.count} of {result.total_picks} picks are in {top.sector}: that is closer to one bet than {top.count}.
        </p>
      )}
    </section>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className={`stat ${accent ? "accent" : ""}`}>
      <b>{num(value)}</b>
      <span>{label}</span>
    </div>
  );
}
