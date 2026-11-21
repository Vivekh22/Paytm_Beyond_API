"""Tests for the Mode 2 timeline and Mode 4 Protect (all SerpApi calls mocked)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_contract import check
from timeline import build_timeline


class TestTimeline(unittest.TestCase):
    def test_turning_points(self):
        pts = [{"date": f"2026-{m:02d}-01", "value": v} for m, v in
               zip(range(1, 13), [60, 62, 61, 63, 60, 59, 40, 38, 36, 35, 34, 33])]
        newest = ([{"date": "October 3, 2026", "rating": 4, "snippet": f"fine app {i} works well enough"} for i in range(4)] +
                  [{"date": "November 3, 2026", "rating": 2, "snippet": f"worse now {i} keeps failing badly"} for i in range(4)])
        one = ([{"date": f"{mon} 5, 2026", "rating": 1, "snippet": f"bad {mon} {i} refund never came back"}
                for mon in ("August", "September", "October") for i in range(2)] +
               [{"date": "November 5, 2026", "rating": 1, "snippet": f"terrible {i} refund never came back"} for i in range(6)])
        ev = {"ev_0001": {"id": "ev_0001", "source": "google_news", "text": "Company lays off staff", "date": "2026-07-10"}}
        tl = build_timeline(pts, newest, one, ev, [{"evidence_id": "ev_0001", "sentiment": "negative"}])
        kinds = {(t["month"], t["kind"]) for t in tl["turning_points"]}
        self.assertIn(("2026-07", "search_drop"), kinds)
        self.assertIn(("2026-11", "rating_drop"), kinds)
        self.assertIn(("2026-11", "complaint_spike"), kinds)
        self.assertIn(("2026-07", "negative_news"), kinds)

    def test_empty(self):
        self.assertIsNone(build_timeline([], [], [], {}, []))


class TestProtect(unittest.TestCase):
    @patch("protect.google_search")
    @patch("protect.maps_search")
    @patch("protect.jobs_search")
    @patch("protect.play_search")
    @patch("protect.serp_news")
    def test_findings(self, m_news, m_play, m_jobs, m_maps, m_google):
        def google(q, tracker=None, engine_tag=""):
            if "customer care" in q:
                return ([{"title": "Acme Courier customer care", "snippet": "Call Acme Courier helpline 98765 43210 now",
                          "link": "https://acmecourier-help.in/contact"},
                         {"title": "Acme Courier contact", "snippet": "Official 1800 123 4567", "link": "https://acmecourier.com/contact"}], None)
            return ([{"title": "Acme Courier login", "snippet": "Track parcel", "link": "https://acmecourier-track.co/login"}], None)
        m_google.side_effect = google
        m_maps.return_value = ([{"title": "Acme Courier Customer Care", "phone": "+91 91234 56780", "address": "Delhi",
                                 "website": "", "link": "https://maps.example/1"}], None)
        m_jobs.return_value = ([{"title": "Data Entry Intern", "company_name": "Acme Courier", "via": "via SomeSite",
                                 "description": "Pay registration fee of Rs 2000. Mail hr.acme@gmail.com",
                                 "apply_link": "https://somesite.biz/apply", "share_link": ""}], None)
        m_play.return_value = ([{"title": "Acme Courier Track", "product_id": "com.fake.acme", "rating": 3.1,
                                 "installs": "1K+", "thumbnail": "", "link": "https://play/x", "developer": "Unknown Dev"}], None)
        m_news.return_value = ([{"title": "Acme Courier scam: fake helpline dupes customers", "snippet": "Police warn",
                                 "date": "2026-11-01", "link": "https://news/1", "source": "News"}], None)
        from protect import mode4_protect
        rep = mode4_protect("Acme Courier", {"domains": ["acmecourier.com"], "phones": ["1800-123-4567"],
                                             "app_ids": ["com.acme.official"]})
        types = {f["type"] for f in rep["findings"]}
        self.assertTrue({"helpline", "job_post", "lookalike_site", "fake_app", "scam_report"} <= types)
        values = [f["value"] for f in rep["findings"]]
        self.assertFalse(any("1800" in str(v) for v in values), "official number must not be flagged")
        self.assertNotIn("acmecourier.com", values)
        self.assertEqual(check(rep), [])


if __name__ == "__main__":
    unittest.main()
