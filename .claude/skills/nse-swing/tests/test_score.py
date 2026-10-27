import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import score  # noqa: E402

FIXTURE = os.path.join(HERE, "fixture.json")


def run(**cfg_overrides):
    cfg = dict(score.DEFAULTS)
    cfg.update(cfg_overrides)
    return score.scan(score.load_rows([FIXTURE]), cfg)


def by_symbol(res):
    return {p["symbol"]: p for p in res["picks"] + res["near_misses"]}


class Filters(unittest.TestCase):
    def setUp(self):
        self.res = run(min_score=0)

    def test_counts(self):
        self.assertEqual(self.res["fetched"], 10)
        self.assertEqual(self.res["in_universe"], 9)      # OUTSIDE is not in Nifty 500
        self.assertEqual(self.res["passed_filters"], 3)   # GOODCO, FINBANK, THIN

    def test_each_filter_drops(self):
        d = self.res["dropped"]
        self.assertEqual(d["debt/equity"], 1)
        self.assertEqual(d["price under"], 1)
        self.assertEqual(d["loss-making (TTM)"], 1)
        self.assertEqual(d["below 200-day average"], 1)
        self.assertEqual(d["market cap"], 1)
        self.assertEqual(d["traded value"], 1)

    def test_finance_exempt_from_debt_filter(self):
        self.assertIn("FINBANK", by_symbol(self.res))

    def test_universe_all(self):
        self.assertEqual(run(universe="ALL")["in_universe"], 10)


class Scoring(unittest.TestCase):
    def setUp(self):
        self.p = by_symbol(run(min_score=0))

    def test_raw_tradingview_keys_normalised(self):
        good = self.p["GOODCO"]   # fixture uses High.1M, SMA50, RSI... for this row
        self.assertTrue(good["breakout"])
        self.assertIn("breakout to a 52-week high", good["strengths"])

    def test_best_stock_ranks_first(self):
        res = run(min_score=0)
        self.assertEqual(res["picks"][0]["symbol"], "GOODCO")
        self.assertGreaterEqual(res["picks"][0]["score"], 85)

    def test_thin_fundamentals_flagged(self):
        self.assertIn("thin fundamental data", self.p["THIN"]["red_flags"])
        self.assertEqual(self.p["THIN"]["fundamental"], 0)

    def test_missing_items_scaled_not_zeroed(self):
        r = {"return_on_equity_fq": 25, "earnings_per_share_diluted_yoy_growth_ttm": 30,
             "total_revenue_yoy_growth_ttm": 25, "price_earnings_ttm": 15}
        f, _, flags = score.fundamental_score(r)    # FCF and margin missing
        self.assertEqual(f, round((12 + 10 + 8 + 8) / 40 * 50, 1))
        self.assertNotIn("thin fundamental data", flags)

    def test_cutoff_and_risk_off(self):
        cfg = dict(score.DEFAULTS)
        rows = score.load_rows([FIXTURE])
        normal = score.scan(rows, cfg)
        off = score.scan(rows, cfg, risk_off=True)
        self.assertEqual(off["cutoff"], normal["cutoff"] + 10)
        self.assertLessEqual(len(off["picks"]), len(normal["picks"]))

    def test_overextended_penalty(self):
        base = {"close": 1000, "sma20": 950, "sma50": 900, "sma200": 800}
        hot = dict(base, sma20=800)
        t1 = score.technical_score(base, None)[0]
        t2, _, flags, _ = score.technical_score(hot, None)
        self.assertEqual(t1 - t2, 5)
        self.assertTrue(any(f.startswith("extended") for f in flags))


class Plan(unittest.TestCase):
    cfg = dict(score.DEFAULTS)

    def test_tighter_of_atr_and_sma50(self):
        # 2xATR = 1000-60 = 940; SMA50 rule = 960*0.99 = 950.4 -> tighter, stop 950.40
        p = score.trade_plan({"close": 1000, "atr": 30, "sma50": 960}, self.cfg)
        self.assertEqual(p["stop"], 950.4)
        self.assertEqual(p["stop_rule"], "just under 50-DMA")
        self.assertEqual(p["target"], 1099.2)

    def test_never_inside_one_atr(self):
        p = score.trade_plan({"close": 1000, "atr": 30, "sma50": 995}, self.cfg)
        self.assertEqual(p["stop"], 970)
        self.assertEqual(p["stop_rule"], "1x ATR (minimum)")

    def test_capped_at_max_risk(self):
        p = score.trade_plan({"close": 1000, "atr": 80, "sma50": 700}, self.cfg)
        self.assertEqual(p["stop"], 920)
        self.assertTrue(p["stop_rule"].startswith("capped"))

    def test_sized_by_max_loss(self):
        p = score.trade_plan({"close": 1000, "atr": 30, "sma50": 900}, self.cfg)
        # stop 940, risk 60 -> 1000 // 60 = 16; cap 20000 // 1000 = 20
        self.assertEqual((p["shares"], p["bound_by"]), (16, "max loss"))
        self.assertLessEqual(p["loss_at_stop"], 1000)

    def test_sized_by_position_cap(self):
        p = score.trade_plan({"close": 5000, "atr": 20, "sma50": 4000}, self.cfg)
        # risk 50 -> 20 by loss; cap 20000 // 5000 = 4
        self.assertEqual((p["shares"], p["bound_by"]), (4, "position cap"))

    def test_stop_on_tick(self):
        p = score.trade_plan({"close": 1234.57, "atr": 21.33, "sma50": 1100}, self.cfg)
        self.assertAlmostEqual(p["stop"] * 20, round(p["stop"] * 20), places=6)


class Format(unittest.TestCase):
    def test_inr(self):
        self.assertEqual(score.fmt_inr(1234567), "₹12,34,567")
        self.assertEqual(score.fmt_inr(999), "₹999")
        self.assertEqual(score.fmt_inr(100000.5, 2), "₹1,00,000.50")

    def test_render_runs(self):
        text = score.render(run(), 5)
        self.assertIn("GOODCO", text)
        self.assertIn("Nothing was placed", text)


if __name__ == "__main__":
    unittest.main()
