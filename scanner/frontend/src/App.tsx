import { useEffect, useState } from "react";
import { api } from "./api";
import { Controls } from "./components/Controls";
import { ResultsTable } from "./components/ResultsTable";
import { Regime, Stats } from "./components/Summary";
import { csv, timeAgo } from "./format";
import type { ScanResult, ScanSettings, Universe } from "./types";

const DEFAULTS: ScanSettings = {
  universe: "CNX500",
  capital: 100000,
  max_loss: 1000,
  max_position_pct: 20,
  min_score: 60,
  risk_mode: "auto",
  top: 100,
};
const STORE_KEY = "nse-scanner-settings";

function loadSettings(): ScanSettings {
  try {
    const saved = localStorage.getItem(STORE_KEY);
    return saved ? { ...DEFAULTS, ...JSON.parse(saved) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

export default function App() {
  const [settings, setSettings] = useState<ScanSettings>(loadSettings);
  const [universes, setUniverses] = useState<Universe[]>([{ id: "CNX500", label: "Nifty 500" }]);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.universes().then(setUniverses).catch(() => undefined);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(settings));
    } catch {
      /* storage unavailable */
    }
  }, [settings]);

  async function runScan(refresh: boolean) {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.scan(settings, refresh));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function exportCsv() {
    if (!result) return;
    const rows: (string | number)[][] = [
      ["Symbol", "Company", "Sector", "Score", "Fundamental", "Technical", "Breakout", "Entry", "Stop", "Target", "Risk %", "Qty", "Position", "Loss at stop", "Strengths", "Red flags"],
      ...result.picks.map((p) => [
        p.symbol, p.company ?? "", p.sector ?? "", p.score, p.fundamental, p.technical, p.breakout ? "yes" : "",
        p.plan.entry, p.plan.stop, p.plan.target, p.plan.risk_pct, p.plan.shares, p.plan.position_value, p.plan.loss_at_stop,
        p.strengths.join("; "), p.red_flags.join("; "),
      ]),
    ];
    const blob = new Blob([csv(rows)], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `nse-swing-${result.universe}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>NSE Swing Scanner</h1>
          <p className="muted">Fundamentals + technicals for Indian stocks · data from TradingView</p>
        </div>
        {result && (
          <div className="meta">
            <span className={`pill ${result.mode}`}>{result.mode === "live" ? "Live data" : "Offline data"}</span>
            <small className="muted">fetched {timeAgo(result.fetched_at)}</small>
          </div>
        )}
      </header>

      <Controls settings={settings} universes={universes} loading={loading} onChange={setSettings} onScan={runScan} />

      {error && <div className="error card">Scan failed: {error}</div>}

      {!result && !error && !loading && (
        <div className="card intro">
          <h3>How it scores</h3>
          <p>
            Stocks must pass hard filters first: price ≥ ₹50, market cap ≥ ₹1,000 cr, ₹5 cr+ traded a day, profitable,
            debt/equity ≤ 1.5 (banks and NBFCs exempt) and above the 200-day average. Then each gets up to <b>50</b> for
            fundamentals (ROE, EPS and revenue growth, margins, free cash flow, valuation) and up to <b>50</b> for
            technicals (trend, relative strength, breakouts, momentum, volume). Every pick comes with a stop, a 2R target
            and a share count sized to your max loss.
          </p>
          <p className="muted">Press Run scan to start.</p>
        </div>
      )}

      {loading && !result && <div className="card intro muted">Fetching ~900 NSE stocks from TradingView…</div>}

      {result && (
        <div className={loading ? "dim" : ""}>
          <Regime result={result} />
          <Stats result={result} />
          <div className="table-head">
            <h2>
              {result.total_picks} picks{result.total_picks > result.picks.length ? ` (top ${result.picks.length} shown)` : ""}
            </h2>
            <button onClick={exportCsv} disabled={!result.picks.length}>
              Export CSV
            </button>
          </div>
          <ResultsTable picks={result.picks} />
          {result.near_misses.length > 0 && (
            <details className="near">
              <summary>Near misses: just under the cutoff ({result.near_misses.length})</summary>
              <ResultsTable picks={result.near_misses} />
            </details>
          )}
        </div>
      )}

      <footer className="muted small">
        A score is arithmetic on public, delayed and sometimes incomplete data. It is not investment advice and cannot see
        results surprises, promoter pledges or news after the fetch. This app never places orders. Consult a
        SEBI-registered adviser for advice.
      </footer>
    </div>
  );
}
