"""NSE swing scanner API.

    uvicorn app:app --port 8000          (from scanner/backend)

Fetches NSE stocks from TradingView, scores them with the nse-swing skill's
score.py (the single source of the scoring rules) and serves the React page
from ../frontend/dist when it has been built. Never places orders.
"""
import os
import sys
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import tradingview as tv

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, ".claude", "skills", "nse-swing"))
import score  # noqa: E402

UNIVERSES = {
    "CNX500": "Nifty 500",
    "NIFTY": "Nifty 50",
    "CNX100": "Nifty 100",
    "CNX200": "Nifty 200",
    "NIFTYMIDCAP150": "Nifty Midcap 150",
    "NIFTYSMLCAP250": "Nifty Smallcap 250",
    "ALL": "900 largest NSE stocks",
}
CACHE = tv.TTLCache(seconds=int(os.environ.get("NSE_SCANNER_CACHE_SECONDS", "300")))

app = FastAPI(title="NSE Swing Scanner", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanRequest(BaseModel):
    universe: str = "CNX500"
    capital: float = Field(100000, gt=0)
    max_loss: float = Field(1000, gt=0)
    max_position_pct: float = Field(20, gt=0, le=100)
    min_score: float = Field(60, ge=0, le=100)
    risk_mode: Literal["auto", "on", "off"] = "auto"   # "off" = force risk-off cutoff
    top: int = Field(50, ge=1, le=500)
    refresh: bool = False


def iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def regime_summary(raw):
    """Risk-off when the Nifty 500 trades below its 50-day average."""
    idx = raw.get("NSE:CNX500") or {}
    close, sma50, sma200 = idx.get("close"), idx.get("sma50"), idx.get("sma200")
    if not (close and sma50):
        return {"status": "unknown", "risk_off": False, "indices": raw,
                "note": "Index data unavailable; using the normal cutoff."}
    risk_off = close < sma50
    if close >= sma50 and (not sma200 or close >= sma200):
        status, note = "risk-on", "Nifty 500 above its 50- and 200-day averages."
    elif risk_off and sma200 and close < sma200:
        status, note = "risk-off", "Nifty 500 below its 50- and 200-day averages: cutoff raised by 10."
    elif risk_off:
        status, note = "risk-off", "Nifty 500 below its 50-day average: cutoff raised by 10."
    else:
        status, note = "mixed", "Nifty 500 above its 50-day but below its 200-day average."
    return {"status": status, "risk_off": risk_off, "indices": raw, "note": note}


def get_regime(refresh=False):
    hit = None if refresh else CACHE.get("regime")
    if not hit:
        try:
            hit = CACHE.put("regime", regime_summary(tv.fetch_regime()))
        except tv.TradingViewError as e:
            return dict(regime_summary({}), note="Index data unavailable (%s); using the normal cutoff." % e), None
    return hit[1], iso(hit[0])


def get_rows(universe, refresh=False):
    key = "rows:" + ",".join("%d-%d" % p for p in tv.PAGES.get(universe, tv.PAGES["CNX500"]))
    hit = None if refresh else CACHE.get(key)
    if not hit:
        try:
            hit = CACHE.put(key, tv.fetch_stocks(universe))
        except tv.TradingViewError as e:
            raise HTTPException(502, str(e))
    return hit[1], iso(hit[0])


@app.get("/api/health")
def health():
    return {"ok": True, "mode": "offline" if tv.is_offline() else "live"}


@app.get("/api/universes")
def universes():
    return [{"id": k, "label": v} for k, v in UNIVERSES.items()]


@app.get("/api/regime")
def regime(refresh: bool = False):
    data, fetched_at = get_regime(refresh)
    return dict(data, fetched_at=fetched_at)


@app.post("/api/scan")
def scan(req: ScanRequest):
    if req.universe not in UNIVERSES:
        raise HTTPException(400, "Unknown universe %r. Use one of: %s" % (req.universe, ", ".join(UNIVERSES)))
    rows, fetched_at = get_rows(req.universe, req.refresh)
    reg, _ = get_regime(req.refresh)
    risk_off = {"auto": reg["risk_off"], "on": False, "off": True}[req.risk_mode]

    cfg = dict(score.DEFAULTS)
    cfg.update(universe=req.universe, capital=req.capital, max_loss=req.max_loss,
               max_position_pct=req.max_position_pct, min_score=req.min_score)
    res = score.scan(rows, cfg, risk_off)

    sectors = {}
    for p in res["picks"]:
        sectors[p["sector"] or "Unknown"] = sectors.get(p["sector"] or "Unknown", 0) + 1
    res["total_picks"] = len(res["picks"])
    res["picks"] = res["picks"][:req.top]
    res.update(
        universe_label=UNIVERSES[req.universe],
        sectors=sorted(({"sector": k, "count": v} for k, v in sectors.items()), key=lambda s: -s["count"]),
        regime=reg,
        fetched_at=fetched_at,
        mode="offline" if tv.is_offline() else "live",
    )
    return res


@app.get("/api/news/{symbol}")
def news(symbol: str):
    sym = symbol.upper()
    if not sym.replace("_", "").replace("&", "").replace("-", "").isalnum():
        raise HTTPException(400, "Bad symbol")
    return {"symbol": sym, "items": tv.fetch_news("NSE:" + sym)}


DIST = os.path.join(REPO, "scanner", "frontend", "dist")
if os.path.isdir(DIST):
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
