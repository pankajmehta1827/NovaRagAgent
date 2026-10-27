---
name: nse-swing
description: >-
  NSE Swing Scanner for the Indian stock market. Scores Nifty 500 (or Nifty
  50/100/200, or all NSE) stocks out of 100 on fundamentals (ROE/ROIC, EPS and
  revenue growth, margins, free cash flow, PEG or P/E, debt/equity) and
  technicals (trend vs 50/200-DMA, relative strength, breakouts and 52-week
  highs, RSI/MACD momentum, volume), after hard filters for price, size,
  liquidity, profits, leverage and the 200-DMA. Checks the market regime first,
  then gives each pick a swing trade plan in rupees: entry, stop (2x ATR or
  under the 50-DMA, max 8%), 2R target and shares sized to your max loss.
  Data from the TradingView connector; optional live prices from Zerodha.
  Never places orders. Use when the user says "scan the Indian market", "best
  NSE stocks", "swing trade ideas", "Nifty 500 scan", "fundamentally strong
  breakouts", "stocks to buy for swing", "technical and fundamental scan",
  "positional picks", or names an Indian stock to score.
argument-hint: "[universe: CNX500 | NIFTY | CNX100 | CNX200 | ALL] [top N]"
---

# nse-swing

Finds Indian stocks that are both **good businesses** and **in good shape on
the chart**, for swing / positional trades held days to a few months. Half the
score is fundamental, half technical, so a great chart on a weak business, or
a great business in a downtrend, does not make the list.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

## Steps

1. **Market regime.** `tradingview_get_ta` (or `tradingview_get_quote`) for
   `NSE:CNX500` and `NSE:NIFTY`. If the index is below its 50-day average, the
   market is **risk-off**: say so up front and pass `--risk-off` (cutoff +10).
   Note the time in IST and whether NSE is open (9:15 to 15:30, Mon-Fri):
   during the session, today's change and volume are partial.

2. **Fetch.** Two `tradingview_screen_assets` calls, identical except `range`
   (`[0, 500]` then `[500, 900]`). The screener's `index` filter returns no
   rows, so fetch NSE by market cap and let the script filter on `indexes`.
   ```
   market: "india"
   filters: {"exchange": "NSE"}
   sort: {"sortBy": "market_cap_basic", "sortOrder": "desc"}
   fields: ["name","description","sector","indexes",
     "close","change","high","relative_volume_10d_calc","average_volume_30d_calc",
     "High.1M","High.3M","price_52_week_high","SMA20","SMA50","SMA200",
     "RSI","MACD.macd","MACD.signal","ATR","Perf.3M","Perf.6M",
     "market_cap_basic","price_earnings_ttm","peg_ratio","return_on_equity_fq",
     "return_on_invested_capital_ttm","net_margin_ttm",
     "earnings_per_share_diluted_yoy_growth_ttm","total_revenue_yoy_growth_ttm",
     "debt_to_equity_fq","free_cash_flow_ttm","net_income_ttm"]
   ```
   The results are too big for the chat and are saved to files; note both
   paths. For Nifty 50/100 the first page alone is enough.

3. **Score.**
   ```bash
   python3 -I "${CLAUDE_SKILL_DIR}/score.py" PAGE1.json PAGE2.json --universe CNX500 --top 15 --write
   python3 -I "${CLAUDE_SKILL_DIR}/score.py" PAGE1.json --universe NIFTY --capital 200000 --max-loss 2000
   ```
   Flags: `--risk-off`, `--min-score N`, `--capital`, `--max-loss`, `--json`,
   `--config PATH` (default `trader/nse-config.json`; copy
   `config.example.json` there to set your own limits), `--write [PATH]`
   (default `trader/nse-swing.json`). Universe ids are the index pronames
   without `NSE:`: `CNX500` (Nifty 500), `NIFTY` (Nifty 50), `CNX100`,
   `CNX200`, `NIFTYMIDCAP150`, `NIFTYSMLCAP250`, or `ALL`. Smallcap 250 runs
   past the 900 largest stocks: add a third page `[900, 1400]` for it.

4. **Check the top 5.** `tradingview_get_news` for each: results dates,
   block deals, regulatory news. **Results due within the trade's likely
   holding period is a red flag** worth stating. If the user is logged in to
   Zerodha, `get_ltp` gives a live price; if it differs from the scan's close
   by more than 1%, re-run the plan maths on the live price.

5. **Report.** Regime line first, then a table: rank, symbol, score
   (fund/tech), entry, stop, target, qty, sector. Under it, one or two lines
   per pick: the strengths, the red flags, the news. Point out sector
   clustering (e.g. 4 of 8 picks in pharma = one bet, not four). End with the
   disclaimer. Ask for capital and max loss if the user has not given them
   (defaults: ₹1,00,000 and ₹1,000).

## How the score works

**Hard filters** (dropped, counted in the summary): price ≥ ₹50, market cap ≥
₹1,000 cr, 30-day traded value ≥ ₹5 cr a day, profitable (TTM), debt/equity ≤
1.5 (not applied to Finance: banks and NBFCs run on leverage), close above the
200-DMA.

**Fundamental, 50:** ROE (or ROIC) 12, EPS growth 10, revenue growth 8, net
margin 5, free cash flow 5, valuation 10 (PEG, else P/E). TradingView leaves
some fields empty for some companies: missing items are left out and the rest
scaled to 50; under half the weight known is scored as is and flagged "thin
fundamental data".

**Technical, 50:** trend stack price > 50-DMA > 200-DMA 12, relative strength
(3- and 6-month return percentile within the index) 12, breakout to a new
1/3-month or 52-week high today 10 (near the 52-week high scores less), RSI
50-70 and MACD above signal 8, volume vs 10-day average 8. Penalties: > 15%
above the 20-DMA (chasing) -5, RSI > 80 -3.

**Plan:** entry = last close. Stop = the tighter of 2x daily ATR and just
under the 50-DMA, never closer than 1 ATR, never more than 8% away, on the
₹0.05 tick. Target = 2R. Shares = the fewer of max loss ÷ risk per share and
max position % of capital; the output says which limit decided it.

## Never

- Never places, modifies or cancels an order, and never offers to from this skill.
- Never calls a pick a recommendation or promises a return.
- Never hides a red flag to make a pick look better.

## Safety

A score is arithmetic on public, delayed, sometimes incomplete data. It is not
advice and cannot see results surprises, promoter pledges, SEBI action or
news after the fetch. A stop can gap: an overnight fall opens below it. Most
traders lose money; size every trade so the loss at the stop is one you can
take. Talk to a SEBI-registered adviser for advice.
