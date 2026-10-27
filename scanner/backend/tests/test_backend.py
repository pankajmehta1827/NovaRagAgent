import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(BACKEND, "..", ".."))
FIXTURE = os.path.join(REPO, ".claude", "skills", "nse-swing", "tests", "fixture.json")
sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

import app as api  # noqa: E402
import tradingview as tv  # noqa: E402


def raw_payload(rows, columns):
    """Shape fixture rows like the live screener: {"data": [{"s", "d": [...]}]}."""
    data = []
    for r in rows:
        norm = {tv.norm_key(k): v for k, v in r.items()}
        data.append({"s": norm["symbol"], "d": [norm.get(tv.norm_key(c)) for c in columns]})
    return {"totalCount": len(data), "data": data}


REGIME_DOWN = {"NSE:CNX500": {"close": 21668, "SMA50": 22664, "SMA200": 22808, "RSI": 38.8},
               "NSE:NIFTY": {"close": 24000, "SMA50": 24500, "SMA200": 24400}}


class Base(unittest.TestCase):
    def setUp(self):
        api.CACHE._store.clear()
        self.client = TestClient(api.app)


class Live(Base):
    """TradingView calls mocked at the HTTP layer."""

    def setUp(self):
        super().setUp()
        with open(FIXTURE) as f:
            self.rows = json.load(f)["data"]
        self.calls = []

        def fake_post(url, body):
            self.calls.append(body)
            if "symbols" in body:   # regime request
                return {"data": [{"s": t, "d": [v.get(c) for c in tv.REGIME_COLUMNS]}
                                 for t, v in REGIME_DOWN.items()]}
            start = body["range"][0]
            return raw_payload(self.rows if start == 0 else [], body["columns"])

        patcher = mock.patch.object(tv, "_post", side_effect=fake_post)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("NSE_SCANNER_OFFLINE", None)

    def test_rows_from_scan_maps_columns(self):
        rows = tv.rows_from_scan({"data": [{"s": "NSE:X", "d": [1, 2]}]}, ["close", "SMA50"])
        self.assertEqual(rows, [{"close": 1, "sma50": 2, "symbol": "NSE:X"}])

    def test_scan_end_to_end(self):
        r = self.client.post("/api/scan", json={"min_score": 0})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["mode"], "live")
        self.assertEqual(body["passed_filters"], 3)
        self.assertEqual(body["picks"][0]["symbol"], "GOODCO")
        self.assertTrue(body["regime"]["risk_off"])
        self.assertEqual(body["cutoff"], 10)            # min_score 0 + 10 risk-off
        self.assertTrue(body["sectors"])

    def test_scan_request_shape(self):
        self.client.post("/api/scan", json={})
        scans = [c for c in self.calls if "range" in c]
        self.assertEqual([c["range"] for c in scans], [[0, 500], [500, 900]])
        self.assertEqual(scans[0]["filter"][0]["right"], "NSE")
        self.assertIn("indexes", scans[0]["columns"])

    def test_risk_mode_override(self):
        body = self.client.post("/api/scan", json={"min_score": 50, "risk_mode": "on"}).json()
        self.assertEqual(body["cutoff"], 50)

    def test_cache_reused_until_refresh(self):
        self.client.post("/api/scan", json={})
        n = len(self.calls)
        self.client.post("/api/scan", json={})
        self.assertEqual(len(self.calls), n)
        self.client.post("/api/scan", json={"refresh": True})
        self.assertGreater(len(self.calls), n)

    def test_user_limits_reach_the_plan(self):
        body = self.client.post("/api/scan", json={"min_score": 0, "max_loss": 5000, "capital": 1000000}).json()
        plan = body["picks"][0]["plan"]
        self.assertLessEqual(plan["loss_at_stop"], 5000)
        self.assertGreater(plan["shares"], 0)

    def test_top_limits_picks_but_counts_all(self):
        body = self.client.post("/api/scan", json={"min_score": 0, "top": 1}).json()
        self.assertEqual(len(body["picks"]), 1)
        self.assertEqual(body["total_picks"], 3)

    def test_bad_universe(self):
        self.assertEqual(self.client.post("/api/scan", json={"universe": "XYZ"}).status_code, 400)

    def test_bad_limits(self):
        self.assertEqual(self.client.post("/api/scan", json={"max_loss": -1}).status_code, 422)

    def test_tradingview_down_is_502(self):
        with mock.patch.object(tv, "_post", side_effect=tv.TradingViewError("boom")):
            r = self.client.post("/api/scan", json={})
        self.assertEqual(r.status_code, 502)

    def test_regime_endpoint(self):
        body = self.client.get("/api/regime").json()
        self.assertEqual(body["status"], "risk-off")


class Offline(Base):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(REGIME_DOWN, self.tmp)
        self.tmp.close()
        patcher = mock.patch.dict(os.environ, {"NSE_SCANNER_OFFLINE": FIXTURE,
                                               "NSE_SCANNER_OFFLINE_REGIME": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(os.unlink, self.tmp.name)

    def test_offline_scan_needs_no_network(self):
        with mock.patch.object(tv, "_post", side_effect=AssertionError("network used")):
            body = self.client.post("/api/scan", json={"min_score": 0}).json()
        self.assertEqual(body["mode"], "offline")
        self.assertEqual(body["picks"][0]["symbol"], "GOODCO")
        self.assertEqual(body["regime"]["status"], "risk-off")

    def test_health_and_news(self):
        self.assertEqual(self.client.get("/api/health").json()["mode"], "offline")
        self.assertEqual(self.client.get("/api/news/GOODCO").json()["items"], [])
        self.assertEqual(self.client.get("/api/news/BAD;SYM").status_code, 400)

    def test_universes(self):
        ids = [u["id"] for u in self.client.get("/api/universes").json()]
        self.assertIn("CNX500", ids)


if __name__ == "__main__":
    unittest.main()
