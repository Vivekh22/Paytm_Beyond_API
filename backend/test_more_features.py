"""Tests for regions, underserved needs, Maps fallback, compare, allowlist/new-only alerts, Extract check, public page."""
import json
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_contract import check

APP = {"title": "App", "product_id": "com.a", "rating": 4.0, "installs": "1M+", "thumbnail": "", "link": "https://p/a"}


def _protect_mocks(brand_flat="acmecourier"):
    return dict(
        google=([{"title": "Acme care", "snippet": "Call 98765 43210", "link": f"https://{brand_flat}-help.in/x"}], None),
        maps=([], None), jobs=([], None), play=([], None), news=([], None),
    )


class TestRegionsAndFallback(unittest.TestCase):
    @patch("serp_client.cached_call")
    def test_regions_parse(self, m):
        m.return_value = ({"interest_by_region": [{"location": "Karnataka", "extracted_value": 100},
                                                  {"location": "Goa", "extracted_value": 0},
                                                  {"location": "Kerala", "value": "64"}]}, False, None)
        from serp_client import trends_regions
        rows, _ = trends_regions("pet care")
        self.assertEqual([r["name"] for r in rows], ["Karnataka", "Kerala"])

    @patch("pipelines.maps_reviews")
    @patch("pipelines.maps_search")
    @patch("pipelines.trends_regions")
    @patch("pipelines.trends_timeseries")
    @patch("pipelines.play_search")
    @patch("pipelines.serp_news")
    @patch("pipelines.serp_reddit")
    @patch("pipelines.you_search")
    def test_mode1_maps_fallback_and_regions(self, you, red, nws, play, tr, reg, ms, mr):
        you.return_value = red.return_value = nws.return_value = ([], None)
        play.return_value = ([], None)
        tr.return_value = ([{"date": "2026-01-01", "value": 40, "anchor": 80}], None)
        reg.return_value = ([{"name": "Karnataka", "value": 100}], None)
        ms.return_value = ([{"title": "Paws Clinic", "phone": "", "address": "", "website": "", "link": "https://maps/1",
                             "data_id": "0x1", "place_id": "p1", "rating": 3.9, "reviews": 120}], None)
        mr.return_value = ([{"user": "A", "rating": 1, "snippet": "Booking was cancelled twice without notice", "date": "2026-11-01", "likes": 2}], None)
        from pipelines import mode1_validate
        r = mode1_validate("Pet grooming at home in Bengaluru")
        self.assertEqual(r["regions"][0]["name"], "Karnataka")
        self.assertEqual(r["competitors"][0]["source"], "google_maps")
        self.assertTrue(any(e["source"] == "google_maps" for e in r["evidence"].values()))
        self.assertEqual(check(r), [])


class TestUnderserved(unittest.TestCase):
    @patch("pipelines.cluster_evidence")
    @patch("pipelines.generate_opportunities", return_value=[])
    @patch("pipelines.trends_timeseries")
    @patch("pipelines.play_search")
    @patch("pipelines.play_reviews")
    @patch("pipelines.serp_reddit", return_value=([], None))
    @patch("pipelines.you_search", return_value=([], None))
    def test_flag(self, you, red, revs, play, tr, opp, cl):
        play.return_value = ([dict(APP, title="A", product_id="a"), dict(APP, title="B", product_id="b")], None)
        revs.side_effect = lambda pid, **k: ([{"id": pid, "user": "u", "rating": 1, "likes": 1,
                                                "snippet": f"Hidden charges on every transfer in {pid} app"}], {}, None)
        tr.return_value = ([{"date": f"2026-{m:02d}-01", "value": 50 + m} for m in range(1, 13)], None)
        cl.side_effect = lambda ev, **k: [{"title": "Hidden charges", "summary": "s", "severity": "high",
                                           "evidence_ids": [e["id"] for e in ev], "_pool": len(ev)}]
        from pipelines import mode3_discover
        r = mode3_discover("Personal Finance")
        c = r["clusters"][0]
        self.assertTrue(c["underserved"], c["underserved_reason"])
        self.assertIn("2 of 2 apps", c["underserved_reason"])


class TestCompare(unittest.TestCase):
    def test_compare(self):
        from compare import compare_reports
        def rep(name, rating, label, neg):
            return {"scan_id": name, "mode": 2, "query": name, "competitors": [{"name": name, "rating": rating}],
                    "verdict": {"label": label}, "trend": {"change_pct": 5}, "timeline": None,
                    "clusters": [{"id": "cl_1", "group": "pain", "title": "Late delivery", "frequency": {"count": 3}}],
                    "news": [{"evidence_id": "x", "sentiment": "negative"}] * neg}
        out = compare_reports(rep("Dunzo", 3.1, "DECLINING", 3), rep("Blinkit", 4.4, "GROWING", 0))
        self.assertEqual(out["leader"]["rating"], "Blinkit")
        self.assertEqual(out["leader"]["fewer_negative_news"], "Blinkit")
        self.assertEqual(out["shared_pains"], ["late delivery"])


class TestProtectExtras(unittest.TestCase):
    def _run(self, brand, extract_text=""):
        m = _protect_mocks(brand.lower().replace(" ", ""))
        with patch("protect.google_search", return_value=m["google"]), patch("protect.maps_search", return_value=m["maps"]), \
             patch("protect.jobs_search", return_value=m["jobs"]), patch("protect.play_search", return_value=m["play"]), \
             patch("protect.serp_news", return_value=m["news"]), patch("protect.extract_page", return_value=(extract_text, None)):
            from protect import mode4_protect
            return mode4_protect(brand, {"domains": [f"{brand.lower().replace(' ', '')}.com"], "phones": ["1800 111 2222"], "app_ids": []})

    def test_allowlist_new_only_and_extract(self):
        brand = f"Acme Courier {uuid.uuid4().hex[:4]}"
        r1 = self._run(brand, extract_text="Enter your password and OTP to continue")
        site = next(f for f in r1["findings"] if f["type"] == "lookalike_site")
        self.assertIn("otp", site["why"])
        self.assertEqual(site["severity"], "high")
        self.assertTrue(all(f["is_new"] for f in r1["findings"]))
        r2 = self._run(brand)
        self.assertFalse(any(f["is_new"] for f in r2["findings"]), "second scan: nothing new")
        from cache import allow_item
        num = next(f for f in r2["findings"] if f["type"] == "helpline")["value"]
        allow_item(brand, "helpline", num)
        r3 = self._run(brand)
        self.assertEqual(r3["allowed_count"], 1)
        self.assertFalse(any(f["type"] == "helpline" for f in r3["findings"]))
        from notify import send_protect_alert
        with patch("notify.TELEGRAM_BOT_TOKEN", "t"), patch("notify.TELEGRAM_CHAT_ID", "c"), patch("notify.requests.post") as post:
            send_protect_alert(r2)
            post.assert_not_called()  # nothing new -> no alert
            send_protect_alert(r1)
            post.assert_called_once()

    def test_public_page_and_endpoints(self):
        from app import app
        c = app.test_client()
        brand = f"Test Brand {uuid.uuid4().hex[:4]}"
        r = c.post("/api/protect/official", json={"brand": brand, "official": {"domains": ["testbrand.com"], "phones": ["1800 000 1111"], "app_ids": ["com.testbrand"]}})
        self.assertEqual(r.status_code, 200)
        page = c.get(f"/verified/{brand}").get_data(as_text=True)
        self.assertIn("testbrand.com", page)
        self.assertIn("1800 000 1111", page)
        self.assertEqual(c.post("/api/protect/watch", json={"brand": brand, "interval_hours": 12}).get_json()["watch"], True)
        c.post("/api/protect/allow", json={"brand": brand, "type": "helpline", "value": "123"})
        self.assertEqual(len(c.get(f"/api/protect/allow?brand={brand}").get_json()), 1)
        c.delete("/api/protect/allow", json={"brand": brand, "type": "helpline", "value": "123"})
        self.assertEqual(len(c.get(f"/api/protect/allow?brand={brand}").get_json()), 0)
        self.assertEqual(c.get("/api/compare?a=nope&b=nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
