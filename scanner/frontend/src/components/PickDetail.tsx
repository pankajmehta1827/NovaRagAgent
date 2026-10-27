import { useEffect, useState } from "react";
import { api } from "../api";
import { rupees } from "../format";
import type { NewsItem, Pick } from "../types";

export function PickDetail({ pick }: { pick: Pick }) {
  const [news, setNews] = useState<NewsItem[] | null>(null);
  const [newsError, setNewsError] = useState<string | null>(null);
  const p = pick.plan;

  useEffect(() => {
    let live = true;
    api
      .news(pick.symbol)
      .then((r) => live && setNews(r.items))
      .catch((e: Error) => live && setNewsError(e.message));
    return () => {
      live = false;
    };
  }, [pick.symbol]);

  return (
    <div className="detail">
      <div className="detail-grid">
        <div>
          <h4>Strengths</h4>
          <ul className="plus">{pick.strengths.length ? pick.strengths.map((s) => <li key={s}>{s}</li>) : <li>–</li>}</ul>
          {pick.red_flags.length > 0 && (
            <>
              <h4>Red flags</h4>
              <ul className="minus">{pick.red_flags.map((s) => <li key={s}>{s}</li>)}</ul>
            </>
          )}
        </div>
        <div>
          <h4>Trade plan</h4>
          <p>
            Buy <b>{p.shares}</b> at {rupees(p.entry)} = {rupees(p.position_value, 0)}.
            <br />
            Stop {rupees(p.stop)}, {p.risk_pct.toFixed(1)}% below entry ({p.stop_rule}) → {rupees(p.loss_at_stop, 0)} lost at the stop.
            <br />
            Target {rupees(p.target)} ({p.reward_risk}R). Size bound by <b>{p.bound_by}</b>.
          </p>
          <p className="muted small">A stop can gap: an overnight fall can open below it.</p>
          <a href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(pick.tv_symbol)}`} target="_blank" rel="noreferrer">
            Open chart on TradingView ↗
          </a>
        </div>
        <div>
          <h4>News</h4>
          {newsError && <p className="muted small">News unavailable ({newsError}).</p>}
          {!newsError && news === null && <p className="muted small">Loading…</p>}
          {news && news.length === 0 && <p className="muted small">No headlines (offline mode or none found).</p>}
          {news && news.length > 0 && (
            <ul className="news">
              {news.map((n, i) => (
                <li key={i}>
                  {n.url ? (
                    <a href={n.url} target="_blank" rel="noreferrer">
                      {n.title}
                    </a>
                  ) : (
                    n.title
                  )}
                  <small>
                    {n.source ?? ""}
                    {n.published ? ` · ${new Date(n.published * 1000).toLocaleDateString("en-IN")}` : ""}
                  </small>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
