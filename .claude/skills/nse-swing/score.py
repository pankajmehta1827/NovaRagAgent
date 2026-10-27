#!/usr/bin/env python3
"""nse-swing: score NSE stocks on fundamentals + technicals for swing trades.

Reads one or more saved TradingView screener results (tradingview_screen_assets
JSON, either {"data": [...]} or a bare list), keeps the members of one index,
drops what fails the hard filters, scores the rest out of 100 (50 fundamental,
50 technical), ranks them and writes a trade plan (entry, stop, 2R target,
shares sized to your max loss) for each pick. Standard library only.

    python3 score.py page1.json page2.json --universe CNX500 --top 15
    python3 score.py page1.json --config trader/nse-config.json --json
    python3 score.py page1.json page2.json --risk-off --write

Nothing here places an order.
"""
import argparse
import json
import math
import os
import sys

DEFAULTS = {
    "capital": 100000,          # rupees available for swing trades
    "max_loss": 1000,           # rupees you accept losing on one trade, at the stop
    "max_position_pct": 20,     # no single position above this % of capital
    "min_score": 60,            # picks must score at least this (risk-off adds 10)
    "universe": "CNX500",       # NSE index proname without "NSE:"; ALL = no index filter
    "min_price": 50,
    "min_market_cap_cr": 1000,
    "min_traded_value_cr": 5,   # 30-day average volume x price
    "max_debt_to_equity": 1.5,  # not applied to the Finance sector
    "atr_stop_mult": 2.0,
    "max_risk_pct": 8.0,
    "target_r": 2.0,
    "tick": 0.05,
}
CRORE = 1e7
FINANCE_SECTORS = {"finance"}


# ---------------------------------------------------------------- loading

def norm_key(k):
    return k.lower().replace(".", "_")


def load_rows(paths):
    """Rows from every file, keys normalised, de-duplicated by symbol."""
    seen, rows = set(), []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        data = doc.get("data", []) if isinstance(doc, dict) else doc
        for r in data:
            r = {norm_key(k): v for k, v in r.items()}
            sym = r.get("symbol") or r.get("name")
            if sym in seen:
                continue
            seen.add(sym)
            rows.append(r)
    return rows


def load_config(path):
    cfg = dict(DEFAULTS)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def num(r, k):
    v = r.get(k)
    if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
        return float(v)
    return None


def in_universe(r, universe):
    if universe.upper() == "ALL":
        return True
    want = "NSE:" + universe.upper()
    return any((i or {}).get("proname", "").upper() == want for i in (r.get("indexes") or []))


# ---------------------------------------------------------------- filters

def hard_filter(r, cfg):
    """None if the stock passes, else the reason it was dropped."""
    close = num(r, "close")
    if close is None:
        return "no price"
    if close < cfg["min_price"]:
        return "price under %s" % fmt_inr(cfg["min_price"])
    mcap = num(r, "market_cap_basic")
    if mcap is not None and mcap < cfg["min_market_cap_cr"] * CRORE:
        return "market cap under %s cr" % cfg["min_market_cap_cr"]
    avg_vol = num(r, "average_volume_30d_calc")
    if avg_vol is not None and avg_vol * close < cfg["min_traded_value_cr"] * CRORE:
        return "traded value under %s cr a day" % cfg["min_traded_value_cr"]
    ni = num(r, "net_income_ttm")
    if ni is not None and ni <= 0:
        return "loss-making (TTM)"
    de = num(r, "debt_to_equity_fq")
    if de is not None and de > cfg["max_debt_to_equity"] and not is_finance(r):
        return "debt/equity %.2f" % de
    sma200 = num(r, "sma200")
    if sma200 is not None and close <= sma200:
        return "below 200-day average"
    return None


def is_finance(r):
    return str(r.get("sector") or "").lower() in FINANCE_SECTORS


# ---------------------------------------------------------------- scoring

def band(value, steps):
    """steps: [(threshold, points), ...] highest first; first threshold met wins."""
    for threshold, points in steps:
        if value >= threshold:
            return points
    return 0


def fundamental_score(r):
    """(score out of 50, positives, flags). Missing items are left out and the
    rest scaled up, unless under half the weight is known."""
    earned, avail, pos, flags = 0.0, 0.0, [], []

    def add(weight, pts, good=None, bad=None):
        nonlocal earned, avail
        earned += pts
        avail += weight
        if good and pts >= weight * 0.7:
            pos.append(good)
        if bad and pts <= weight * 0.3:
            flags.append(bad)

    roe = num(r, "return_on_equity_fq")
    roic = num(r, "return_on_invested_capital_ttm")
    q = roe if roe is not None else roic
    if q is not None:
        label = "ROE" if roe is not None else "ROIC"
        add(12, band(q, [(20, 12), (15, 8), (10, 4)]),
            "%s %.0f%%" % (label, q), "weak %s %.0f%%" % (label, q))

    eps_g = num(r, "earnings_per_share_diluted_yoy_growth_ttm")
    if eps_g is not None:
        add(10, band(eps_g, [(25, 10), (15, 7), (5, 4), (0.0001, 2)]),
            "EPS +%.0f%% YoY" % eps_g, "EPS %+.0f%% YoY" % eps_g)

    rev_g = num(r, "total_revenue_yoy_growth_ttm")
    if rev_g is not None:
        add(8, band(rev_g, [(20, 8), (12, 6), (5, 3), (0.0001, 1)]),
            "revenue +%.0f%% YoY" % rev_g, "revenue %+.0f%% YoY" % rev_g)

    nm = num(r, "net_margin_ttm")
    if nm is not None:
        add(5, band(nm, [(15, 5), (8, 3), (0.0001, 1)]), "net margin %.0f%%" % nm, None)

    fcf = num(r, "free_cash_flow_ttm")
    if fcf is not None:
        add(5, 5 if fcf > 0 else 0, None, "negative free cash flow")

    peg = num(r, "peg_ratio")
    pe = num(r, "price_earnings_ttm")
    if peg is not None and peg > 0:
        add(10, band(-peg, [(-1, 10), (-1.5, 7), (-2, 4)]),
            "PEG %.1f" % peg, "PEG %.1f" % peg)
    elif pe is not None and pe > 0:
        add(10, band(-pe, [(-20, 8), (-35, 6), (-50, 3), (-80, 1)]),
            "P/E %.0f" % pe, "rich P/E %.0f" % pe)

    if avail >= 25:
        score = earned / avail * 50
    else:
        score = earned
        flags.append("thin fundamental data")
    return round(score, 1), pos, flags


def percentile_ranks(rows, key):
    vals = sorted(v for v in (num(r, key) for r in rows) if v is not None)
    n = len(vals)
    out = {}
    for r in rows:
        v = num(r, key)
        if v is None or n < 2:
            continue
        below = sum(1 for x in vals if x < v)
        out[id(r)] = below / (n - 1)
    return out


def technical_score(r, rs):
    """(score out of 50, positives, flags, is_breakout). rs = 0..1 relative strength or None."""
    s, pos, flags = 0.0, [], []
    close = num(r, "close")
    sma20, sma50, sma200 = num(r, "sma20"), num(r, "sma50"), num(r, "sma200")

    if sma50 and sma200:
        if close > sma50 > sma200:
            s += 12
            pos.append("uptrend (price > 50-DMA > 200-DMA)")
        elif close > sma50 and close > sma200:
            s += 8
        elif close > sma200:
            s += 4
            flags.append("below 50-day average")

    if rs is not None:
        s += 12 * rs
        if rs >= 0.8:
            pos.append("top %d%% relative strength" % max(1, round((1 - rs) * 100)))
        elif rs < 0.3:
            flags.append("weak relative strength")

    high, h1m, h3m, h52 = num(r, "high"), num(r, "high_1m"), num(r, "high_3m"), num(r, "price_52_week_high")
    breakout = bool(high and h1m and high >= h1m * 0.9999 and close >= h1m * 0.99)
    if breakout and h52 and close >= h52 * 0.99:
        s += 10
        pos.append("breakout to a 52-week high")
    elif breakout:
        s += 10
        pos.append("breakout to a %s high" % ("3-month" if h3m and close >= h3m * 0.99 else "1-month"))
    elif h52 and close >= h52 * 0.95:
        s += 8
        pos.append("within 5% of 52-week high")
    elif h52 and close >= h52 * 0.90:
        s += 6
    elif h3m and close >= h3m * 0.85:
        s += 3

    rsi = num(r, "rsi")
    if rsi is not None:
        if 50 <= rsi <= 70:
            s += 5
        elif 45 <= rsi < 50 or 70 < rsi <= 78:
            s += 2
        if rsi > 80:
            s -= 3
            flags.append("RSI %.0f overbought" % rsi)
    macd, sig = num(r, "macd_macd"), num(r, "macd_signal")
    if macd is not None and sig is not None and macd > sig:
        s += 3

    rv = num(r, "relative_volume_10d_calc")
    if rv is not None:
        s += band(rv, [(2, 8), (1.5, 6), (1.0, 3)])
        if rv >= 1.5:
            pos.append("volume %.1fx average" % rv)

    if sma20 and close > sma20 * 1.15:
        s -= 5
        flags.append("extended %.0f%% above 20-DMA" % ((close / sma20 - 1) * 100))

    return round(max(s, 0), 1), pos, flags, breakout


# ---------------------------------------------------------------- trade plan

def round_down(x, tick):
    return math.floor(x / tick + 1e-9) * tick


def round_up(x, tick):
    return math.ceil(x / tick - 1e-9) * tick


def trade_plan(r, cfg):
    entry = num(r, "close")
    atr = num(r, "atr")
    sma50 = num(r, "sma50")
    tick = cfg["tick"]
    candidates, rule = [], None
    if atr:
        candidates.append((entry - cfg["atr_stop_mult"] * atr, "%gx ATR" % cfg["atr_stop_mult"]))
    if sma50 and sma50 < entry:
        candidates.append((sma50 * 0.99, "just under 50-DMA"))
    if candidates:
        stop, rule = max(candidates)          # the tighter of the two
        if atr and entry - stop < atr:        # never inside one day's normal range
            stop, rule = entry - atr, "1x ATR (minimum)"
    else:
        stop, rule = entry * (1 - cfg["max_risk_pct"] / 100), "max risk %"
    floor_stop = entry * (1 - cfg["max_risk_pct"] / 100)
    if stop < floor_stop:
        stop, rule = floor_stop, "capped at %g%% risk" % cfg["max_risk_pct"]
    stop = round_down(stop, tick)
    risk = entry - stop
    target = round_up(entry + cfg["target_r"] * risk, tick)

    by_loss = int(cfg["max_loss"] // risk) if risk > 0 else 0
    by_cap = int(cfg["capital"] * cfg["max_position_pct"] / 100 // entry)
    shares = min(by_loss, by_cap)
    bound = "max loss" if by_loss <= by_cap else "position cap"
    return {
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "stop_rule": rule,
        "target": round(target, 2),
        "risk_per_share": round(risk, 2),
        "risk_pct": round(risk / entry * 100, 2),
        "reward_risk": cfg["target_r"],
        "shares": shares,
        "bound_by": bound,
        "position_value": round(shares * entry, 2),
        "loss_at_stop": round(shares * risk, 2),
    }


# ---------------------------------------------------------------- run

def scan(rows, cfg, risk_off=False):
    universe = [r for r in rows if in_universe(r, cfg["universe"])]
    rs3 = percentile_ranks(universe, "perf_3m")
    rs6 = percentile_ranks(universe, "perf_6m")
    dropped, scored = {}, []
    for r in universe:
        why = hard_filter(r, cfg)
        if why:
            key = _reason_bucket(why)
            dropped[key] = dropped.get(key, 0) + 1
            continue
        parts = [x for x in (rs3.get(id(r)), rs6.get(id(r))) if x is not None]
        rs = sum(parts) / len(parts) if parts else None
        f, fpos, fflags = fundamental_score(r)
        t, tpos, tflags, breakout = technical_score(r, rs)
        scored.append({
            "symbol": r.get("name") or r.get("symbol"),
            "tv_symbol": r.get("symbol"),
            "company": r.get("description"),
            "sector": r.get("sector"),
            "score": round(f + t, 1),
            "fundamental": f,
            "technical": t,
            "breakout": breakout,
            "change_pct": num(r, "change"),
            "strengths": fpos + tpos,
            "red_flags": fflags + tflags,
            "plan": trade_plan(r, cfg),
        })
    scored.sort(key=lambda x: -x["score"])
    cutoff = cfg["min_score"] + (10 if risk_off else 0)
    picks = [s for s in scored if s["score"] >= cutoff]
    return {
        "universe": cfg["universe"],
        "fetched": len(rows),
        "in_universe": len(universe),
        "passed_filters": len(scored),
        "dropped": dropped,
        "cutoff": cutoff,
        "risk_off": risk_off,
        "picks": picks,
        "near_misses": [s for s in scored if s["score"] < cutoff][:5],
        "config": {k: cfg[k] for k in ("capital", "max_loss", "max_position_pct")},
    }


def _reason_bucket(why):
    for prefix in ("debt/equity", "price under", "market cap", "traded value"):
        if why.startswith(prefix):
            return prefix
    return why


def fmt_inr(x, decimals=0):
    """Indian digit grouping: 1234567.5 -> ₹12,34,567."""
    neg = x < 0
    s = ("%.*f" % (decimals, abs(x)))
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + "₹" + whole + ("." + frac if frac else "")


def render(res, top):
    out = []
    out.append("NSE swing scan: %s | fetched %d, in index %d, passed filters %d, picks %d (score >= %d%s)"
               % (res["universe"], res["fetched"], res["in_universe"], res["passed_filters"],
                  len(res["picks"]), res["cutoff"], ", risk-off" if res["risk_off"] else ""))
    if res["dropped"]:
        out.append("Dropped: " + ", ".join("%s %d" % (k, v) for k, v in sorted(res["dropped"].items(), key=lambda kv: -kv[1])))
    if res["in_universe"] == 0:
        out.append("No stocks matched the index. Check --universe and that the fetch included the 'indexes' field.")
    out.append("")
    out.append("%-3s %-12s %5s %5s %5s %10s %10s %10s %6s %6s  %s"
               % ("#", "Symbol", "Score", "Fund", "Tech", "Entry", "Stop", "Target", "Risk%", "Qty", "Sector"))
    for i, p in enumerate(res["picks"][:top], 1):
        pl = p["plan"]
        out.append("%-3d %-12s %5.1f %5.1f %5.1f %10s %10s %10s %6.1f %6d  %s"
                   % (i, p["symbol"] + ("*" if p["breakout"] else ""), p["score"], p["fundamental"], p["technical"],
                      fmt_inr(pl["entry"], 2), fmt_inr(pl["stop"], 2), fmt_inr(pl["target"], 2),
                      pl["risk_pct"], pl["shares"], p["sector"] or ""))
    if not res["picks"]:
        out.append("(no stock reached the cutoff)")
    out.append("* = breakout today. Qty sized to max loss %s, capital %s, max %d%% a position."
               % (fmt_inr(res["config"]["max_loss"]), fmt_inr(res["config"]["capital"]), res["config"]["max_position_pct"]))
    out.append("")
    for p in res["picks"][:top]:
        pl = p["plan"]
        out.append("%s  %s" % (p["symbol"], p["company"] or ""))
        out.append("  + " + ("; ".join(p["strengths"]) or "-"))
        if p["red_flags"]:
            out.append("  - " + "; ".join(p["red_flags"]))
        out.append("  plan: buy %d @ %s, stop %s (%s), target %s (%gR); %s at stop; bound by %s"
                   % (pl["shares"], fmt_inr(pl["entry"], 2), fmt_inr(pl["stop"], 2), pl["stop_rule"],
                      fmt_inr(pl["target"], 2), pl["reward_risk"], fmt_inr(pl["loss_at_stop"]), pl["bound_by"]))
    out.append("")
    out.append("A score is a rules check on public data, not advice. Nothing was placed.")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+", help="saved tradingview_screen_assets JSON results")
    ap.add_argument("--universe", help="index proname without NSE:, e.g. CNX500, NIFTY, CNX100, CNX200; ALL")
    ap.add_argument("--config", default="trader/nse-config.json")
    ap.add_argument("--capital", type=float)
    ap.add_argument("--max-loss", type=float)
    ap.add_argument("--min-score", type=float)
    ap.add_argument("--risk-off", action="store_true", help="index below its 50-DMA: cutoff +10")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", nargs="?", const="trader/nse-swing.json")
    a = ap.parse_args(argv)

    cfg = load_config(a.config)
    for k, v in (("universe", a.universe), ("capital", a.capital), ("max_loss", a.max_loss), ("min_score", a.min_score)):
        if v is not None:
            cfg[k] = v
    res = scan(load_rows(a.files), cfg, a.risk_off)
    if a.write:
        os.makedirs(os.path.dirname(a.write) or ".", exist_ok=True)
        with open(a.write, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, ensure_ascii=False)
    print(json.dumps(res, indent=2, ensure_ascii=False) if a.json else render(res, a.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
