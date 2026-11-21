import json
import os
import sys
import time
from pathlib import Path
import unittest

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app import app
from cache import (
    cached_call,
    clean_params_dict,
    get_cache_stats,
    get_report,
    init_db,
    make_cache_key,
    save_report,
)
from evidence import EvidenceCollector
from prewarm import estimate_serpapi_calls
from scoring import (
    compute_discovery_verdict,
    compute_trajectory,
    compute_trend_metrics,
    compute_viability_score,
)


class TestContractValidation(unittest.TestCase):
    """Validate that mock reports adhere 100% to the shared JSON contract."""

    REQUIRED_ROOT_KEYS = {
        "scan_id",
        "mode",
        "query",
        "generated_at",
        "keywords",
        "credits",
        "verdict",
        "trend",
        "competitors",
        "clusters",
        "opportunities",
        "news",
        "evidence",
        "warnings",
    }

    def _validate_report_contract(self, report: dict, expected_mode: int):
        for k in self.REQUIRED_ROOT_KEYS:
            self.assertIn(k, report, f"Missing required root key: {k}")

        self.assertEqual(report["mode"], expected_mode)
        evidence_map = report["evidence"]
        self.assertIsInstance(evidence_map, dict)

        # Invariant: Every evidence_ids reference MUST exist in evidence map
        for c in report["clusters"]:
            for eid in c.get("evidence_ids", []):
                self.assertIn(
                    eid,
                    evidence_map,
                    f"Cluster '{c.get('id')}' references missing evidence ID '{eid}'",
                )

        for op in report["opportunities"]:
            for eid in op.get("evidence_ids", []):
                self.assertIn(
                    eid,
                    evidence_map,
                    f"Opportunity '{op.get('id')}' references missing evidence ID '{eid}'",
                )

        for n in report["news"]:
            eid = n.get("evidence_id")
            if eid:
                self.assertIn(
                    eid,
                    evidence_map,
                    f"News references missing evidence ID '{eid}'",
                )

        for factor in report["verdict"].get("breakdown", []):
            for eid in factor.get("evidence_ids", []):
                self.assertIn(
                    eid,
                    evidence_map,
                    f"Verdict breakdown factor '{factor.get('factor')}' references missing evidence ID '{eid}'",
                )

    def test_mock_report_mode1(self):
        path = backend_dir / "mock" / "report_mode1.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._validate_report_contract(data, 1)
        self.assertEqual(data["verdict"]["kind"], "viability")
        self.assertIn(data["verdict"]["label"], ["BUILD", "PIVOT", "KILL"])

    def test_mock_report_mode2(self):
        path = backend_dir / "mock" / "report_mode2.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._validate_report_contract(data, 2)
        self.assertEqual(data["verdict"]["kind"], "trajectory")
        self.assertIn(
            data["verdict"]["label"], ["GROWING", "STAGNATING", "DECLINING"]
        )
        # Check that strength clusters exist
        groups = {c.get("group") for c in data["clusters"]}
        self.assertIn("strength", groups)

    def test_mock_report_mode3(self):
        path = backend_dir / "mock" / "report_mode3.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._validate_report_contract(data, 3)
        self.assertEqual(data["verdict"]["kind"], "discovery")


class TestCacheAndLimiter(unittest.TestCase):
    """Test SQLite caching, key hashing, and rate limiting."""

    def test_make_cache_key_strips_sensitive_keys(self):
        params1 = {"q": "shoes", "api_key": "secret123", "gl": "in"}
        params2 = {"gl": "in", "q": "shoes", "api_key": "different_secret"}
        key1 = make_cache_key("serpapi", "search", params1)
        key2 = make_cache_key("serpapi", "search", params2)
        self.assertEqual(key1, key2)

    def test_cached_call_execution_and_hit(self):
        call_count = [0]
        test_nonce = str(time.time())

        def dummy_fetch():
            call_count[0] += 1
            return {"result": "success", "count": call_count[0]}

        params = {"test_query": f"unit_test_probe_{test_nonce}"}
        # First call (miss)
        data1, cached1, warn1 = cached_call(
            "test_provider", "test_engine", params, dummy_fetch
        )
        self.assertFalse(cached1)
        self.assertEqual(call_count[0], 1)
        self.assertEqual(data1["count"], 1)

        # Second call (hit)
        data2, cached2, warn2 = cached_call(
            "test_provider", "test_engine", params, dummy_fetch
        )
        self.assertTrue(cached2)
        self.assertEqual(call_count[0], 1)  # fetch not called again
        self.assertEqual(data2["count"], 1)

    def test_report_persistence(self):
        scan_id = "test_scan_xyz"
        dummy_report = {"scan_id": scan_id, "status": "verified"}
        save_report(scan_id, 1, "test query", dummy_report)
        retrieved = get_report(scan_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["status"], "verified")


class TestEvidenceCollector(unittest.TestCase):
    """Test evidence normalization, deduplication, and ID mapping."""

    def test_evidence_processing(self):
        collector = EvidenceCollector(max_items=5)
        reviews = [
            {
                "id": "r1",
                "user": "Alice",
                "rating": 1,
                "snippet": "This app is completely broken and crashes on payment.",
                "likes": 10,
            },
            {
                "id": "r2",
                "user": "Bob",
                "rating": 1,
                "snippet": "This app is completely broken and crashes on payment.",  # duplicate
                "likes": 5,
            },
            {
                "id": "r3",
                "user": "Charlie",
                "rating": 1,
                "snippet": "Too short",  # < 20 chars, should be dropped
                "likes": 0,
            },
            {
                "id": "r4",
                "user": "Dave",
                "rating": 1,
                "snippet": "UPI transaction tracking does not sync with ICICI bank properly.",
                "likes": 25,
            },
        ]
        collector.add_play_reviews(
            reviews, app_name="TestApp", app_url="https://play.google.com/test"
        )
        ev_map, ev_list = collector.build()

        # Should have kept 2 unique items (r4 and r1, sorted by likes descending)
        self.assertEqual(len(ev_list), 2)
        self.assertIn("ev_0001", ev_map)
        self.assertIn("ev_0002", ev_map)
        self.assertEqual(ev_map["ev_0001"]["likes"], 25)
        self.assertEqual(ev_map["ev_0002"]["likes"], 10)


class TestScoringEngine(unittest.TestCase):
    """Test deterministic scoring math."""

    def test_viability_score_calculation(self):
        trend_points = [{"date": f"2026-{m:02d}", "value": 70} for m in range(1, 13)]
        evidence_map = {
            f"ev_{i:04d}": {
                "id": f"ev_{i:04d}",
                "source": "play_store",
                "entity": "AppA",
            }
            for i in range(1, 50)
        }
        clusters = [
            {
                "id": "cl_1",
                "group": "pain",
                "frequency": {"count": 30},
                "evidence_ids": [f"ev_{i:04d}" for i in range(1, 31)],
            }
        ]
        competitors = [{"name": "AppA", "rating": 3.5}]

        verdict = compute_viability_score(
            trend_points=trend_points,
            clusters=clusters,
            competitors=competitors,
            evidence_map=evidence_map,
            total_reviews_scanned=40,
        )

        self.assertEqual(verdict["kind"], "viability")
        self.assertIsInstance(verdict["score"], int)
        self.assertIn(verdict["label"], ["BUILD", "PIVOT", "KILL"])
        self.assertEqual(len(verdict["breakdown"]), 5)

    def test_trajectory_calculation(self):
        trend_points = [{"date": "2026-01", "value": 30}, {"date": "2026-11", "value": 80}]
        newest_reviews = [{"id": "ev_0001", "rating": 5}, {"id": "ev_0002", "rating": 5}]
        news_class = [{"evidence_id": "ev_0003", "sentiment": "positive"}]
        evidence_map = {
            "ev_0001": {},
            "ev_0002": {},
            "ev_0003": {},
        }

        verdict = compute_trajectory(
            trend_points=trend_points,
            all_time_rating=3.0,
            newest_reviews=newest_reviews,
            news_classifications=news_class,
            evidence_map=evidence_map,
        )
        self.assertEqual(verdict["kind"], "trajectory")
        self.assertEqual(verdict["label"], "GROWING")


class TestFlaskEndpoints(unittest.TestCase):
    """Test Flask routes using test_client."""

    def setUp(self):
        self.client = app.test_client()

    def test_health_endpoint(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("serpapi_live_calls_this_hour", data)
        self.assertIn("cache_entries", data)
        self.assertIn("demo_mode", data)

    def test_examples_endpoint(self):
        resp = self.client.get("/api/examples")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 11)

    def test_mock_endpoints(self):
        for mode in (1, 2, 3):
            resp = self.client.get(f"/api/mock/{mode}")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertEqual(data["mode"], mode)

    def test_prewarm_dry_run_estimation(self):
        est = estimate_serpapi_calls()
        self.assertEqual(len(est["presets"]), 11)
        self.assertEqual(est["total_estimated_serpapi_calls"], 85)  # 3x8 + 3x7 + 3x8 + 2x8

    def test_scan_and_stream_endpoints(self):
        resp = self.client.post("/api/scan", json={"mode": 1, "query": "Test Scanner"})
        self.assertEqual(resp.status_code, 202)
        data = resp.get_json()
        self.assertIn("scan_id", data)
        scan_id = data["scan_id"]

        stream_resp = self.client.get(f"/api/scan/{scan_id}/stream")
        self.assertEqual(stream_resp.status_code, 200)
        self.assertEqual(stream_resp.mimetype, "text/event-stream")



from unittest.mock import patch

class TestPipelinesEndToEnd(unittest.TestCase):
    """Test full pipeline execution flow for all 3 modes."""

    @patch("pipelines.trends_timeseries")
    @patch("pipelines.play_search")
    @patch("pipelines.play_reviews")
    @patch("pipelines.serp_news")
    @patch("pipelines.serp_reddit")
    @patch("pipelines.you_search")
    def test_mode1_pipeline_flow(self, mock_you, mock_reddit, mock_news, mock_revs, mock_play, mock_trends):
        mock_trends.return_value = ([{"date": "2026-01", "value": 50}], None)
        mock_play.return_value = ([{"title": "TestApp", "product_id": "com.test", "rating": 4.0, "installs": "1M+", "thumbnail": "", "link": "https://play.google.com/test"}], None)
        mock_revs.return_value = ([{"id": "r1", "user": "U1", "rating": 1, "snippet": "Frequent crashes on checkout and bad customer care.", "likes": 5}], {"rating": 4.0, "reviews": 100}, None)
        mock_news.return_value = ([{"title": "Tech startup raises funding", "source": "News", "date": "today", "link": "https://news.com", "snippet": "Expansion plans."}], None)
        mock_reddit.return_value = ([{"title": "Reddit review", "snippet": "Users discuss problems.", "link": "https://reddit.com"}], None)
        mock_you.return_value = ([{"title": "Web result", "url": "https://web.com", "snippet": "Market report and competitors.", "kind": "web"}], None)

        from pipelines import mode1_validate
        events = []
        report = mode1_validate("Test Idea", progress_callback=lambda s, m, p: events.append((s, p)))

        self.assertIn("scan_id", report)
        self.assertEqual(report["mode"], 1)
        self.assertIn("verdict", report)
        self.assertTrue(len(events) > 0)
        self.assertEqual(events[-1][1], 100)

    @patch("pipelines.trends_timeseries")
    @patch("pipelines.play_search")
    @patch("pipelines.play_reviews")
    @patch("pipelines.serp_news")
    @patch("pipelines.serp_reddit")
    @patch("pipelines.you_search")
    def test_mode2_pipeline_flow(self, mock_you, mock_reddit, mock_news, mock_revs, mock_play, mock_trends):
        mock_play.return_value = ([{"title": "TargetCo", "product_id": "com.target", "rating": 3.8, "installs": "5M+", "thumbnail": "", "link": "https://play.google.com/target"}], None)
        mock_revs.return_value = ([{"id": "r1", "user": "U1", "rating": 1, "snippet": "Terrible delivery delay and cancellation.", "likes": 2}], {"rating": 3.8, "reviews": 500}, None)
        mock_news.return_value = ([{"title": "Layoffs announced", "source": "News", "date": "today", "link": "https://news.com", "snippet": "Financial strain."}], None)
        mock_trends.return_value = ([{"date": "2026-01", "value": 40}], None)
        mock_reddit.return_value = ([], None)
        mock_you.return_value = ([], None)

        from pipelines import mode2_investigate
        events = []
        report = mode2_investigate("TargetCo", progress_callback=lambda s, m, p: events.append((s, p)))

        self.assertEqual(report["mode"], 2)
        self.assertEqual(report["verdict"]["kind"], "trajectory")

    @patch("pipelines.trends_timeseries")
    @patch("pipelines.play_search")
    @patch("pipelines.play_reviews")
    @patch("pipelines.serp_news")
    @patch("pipelines.serp_reddit")
    @patch("pipelines.you_search")
    def test_mode3_pipeline_flow(self, mock_you, mock_reddit, mock_news, mock_revs, mock_play, mock_trends):
        mock_play.return_value = ([{"title": f"App{i}", "product_id": f"com.app{i}", "rating": 4.1, "installs": "1M+", "thumbnail": "", "link": f"https://play.google.com/app{i}"} for i in range(3)], None)
        mock_revs.return_value = ([{"id": "r1", "user": "U1", "rating": 1, "snippet": "Systemic payment and invoice generation bug across apps.", "likes": 8}], {"rating": 4.1, "reviews": 200}, None)
        mock_trends.return_value = ([{"date": "2026-01", "value": 60}], None)
        mock_reddit.return_value = ([], None)
        mock_you.return_value = ([], None)

        from pipelines import mode3_discover
        events = []
        report = mode3_discover("Fintech Category", progress_callback=lambda s, m, p: events.append((s, p)))

        self.assertEqual(report["mode"], 3)
        self.assertEqual(report["verdict"]["kind"], "discovery")


if __name__ == "__main__":
    unittest.main()
