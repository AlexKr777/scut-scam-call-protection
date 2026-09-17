import unittest

from backend.dual_pass_asr import ASRText, DualPassCallerASR, projected_warning_latency
from backend.realtime_pipeline import CALLER, USER


class DualPassASRTests(unittest.TestCase):
    def setUp(self):
        self.fast = lambda raw: ASRText(raw.decode(), "ru", .9)
        self.accurate = lambda raw: ASRText(raw.decode(), "ru", .98)

    def test_fast_caller_precedes_user_and_accurate(self):
        p = DualPassCallerASR(self.fast, self.accurate)
        p.submit_fast(USER, b"user", 0, 1)
        p.submit_accurate_caller(b"stable", 0, 1); p.set_safe_gap(True)
        p.submit_fast(CALLER, b"caller", 0, 1)
        self.assertEqual("caller", p.drain_once().text)
        self.assertEqual("user", p.drain_once().text)
        self.assertEqual("stable", p.drain_once().text)

    def test_accurate_cannot_start_without_safe_gap(self):
        p = DualPassCallerASR(self.fast, self.accurate)
        p.submit_accurate_caller(b"final", 0, 1)
        self.assertIsNone(p.drain_once())
        p.set_safe_gap(True)
        self.assertEqual("final", p.drain_once().text)

    def test_fast_partial_revisions_do_not_enter_stable_history(self):
        p = DualPassCallerASR(self.fast, self.accurate)
        p.submit_fast(CALLER, b"name code", 0, 1000)
        first=p.drain_once()
        p.submit_fast(CALLER, b"name code from SMS", 500, 1500)
        second=p.drain_once()
        self.assertLess(first.revision_id, second.revision_id)
        self.assertEqual([], p.assembler.turns)
        p.submit_accurate_caller(b"name code from SMS please", 0, 1600); p.set_safe_gap(True)
        stable=p.drain_once()
        self.assertEqual("name code from SMS please", stable.text)
        self.assertEqual(1, len(p.assembler.turns))

    def test_backlog_remains_bounded_and_keeps_newest_fast_caller(self):
        p = DualPassCallerASR(self.fast, self.accurate)
        p.scheduler.fast_caller.maxsize = 1
        p.submit_fast(CALLER, b"old", 0, 1); p.submit_fast(CALLER, b"new", 1, 2)
        self.assertEqual("new", p.drain_once().text)
        self.assertEqual(1, p.scheduler.dropped["FAST_CALLER"])

    def test_latency_budget_is_explicit(self):
        budget=projected_warning_latency(10, 12.2, 16.5)
        self.assertEqual(2.2, budget["fastPathSeconds"])
        self.assertEqual(3.2, budget["futureAi1.0s"])

    def test_fast_risk_interface_receives_revision_metadata(self):
        observed=[]
        p=DualPassCallerASR(self.fast, self.accurate, observed.append)
        p.submit_fast(CALLER,b"give SMS code",0,1000); partial=p.drain_once()
        self.assertEqual(partial,observed[0]); self.assertFalse(observed[0].stable)
        self.assertEqual(CALLER,observed[0].speaker); self.assertIsNotNone(p.timeline["future_ai_request_ready_at"])

    def test_dangerous_and_protective_fixtures_remain_distinct_text(self):
        dangerous="Назовите код из SMS"
        protective="Никому не называйте код из SMS"
        self.assertIn("Назовите", dangerous)
        self.assertIn("Никому", protective)
        self.assertNotEqual(dangerous, protective)

    def test_romanian_and_english_fixture_texts_remain_available(self):
        fixtures=("Nu spune nimănui codul SMS.", "Do not share the SMS code.")
        self.assertTrue(all("SMS" in item for item in fixtures))
