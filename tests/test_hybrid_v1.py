from __future__ import annotations
import unittest

from backend.hybrid_v1 import HybridBrainV1, NomicSignal, RiskLevel, detect_languages, normalize
from backend.realtime_pipeline import CALLER, USER, Utterance


def turn(speaker: str, text: str, number: int = 1) -> Utterance:
    return Utterance(str(number), speaker, text, 0, 0, True)


class HybridV1Tests(unittest.TestCase):
    def ingest(self, text: str, speaker: str = CALLER, score: float = 0.0):
        brain = HybridBrainV1(); return brain.ingest(turn(speaker, text), NomicSignal(score, source="TEST"))

    def test_normalization_and_per_turn_language_detection(self):
        self.assertEqual(normalize("  NEVER   TELL "), "never tell")
        self.assertEqual(set(detect_languages("Spune codul from SMS")), {"ro", "en"})
        self.assertEqual(detect_languages("Назовите код"), ("ru",))

    def test_explicit_otp_is_high_risk_even_with_low_nomic(self):
        result = self.ingest("Please read the six digits from the SMS", score=.08)
        self.assertEqual(result["risk_level"], "HIGH_RISK")
        self.assertIn("REQUEST_OTP", result["requested_actions"])
        self.assertTrue(result["alert_recommended"])

    def test_safe_account_and_remote_access_are_critical_rule_gates(self):
        self.assertEqual(self.ingest("Move your money to the safe account", score=.1)["risk_level"], "HIGH_RISK")
        self.assertEqual(self.ingest("Install AnyDesk and allow remote access", score=.1)["risk_level"], "HIGH_RISK")

    def test_protective_context_suppresses_unexplained_high_nomic(self):
        result = self.ingest("Never give a verification code to a caller.", score=.95)
        self.assertEqual(result["risk_level"], "WATCH")
        codes = {x["code"] for x in result["protective_context"]}
        self.assertTrue({"PROTECTIVE_ADVICE", "NEGATION"} <= codes)

    def test_user_repetition_never_creates_action(self):
        result = self.ingest("Are you asking me for the SMS code?", USER)
        self.assertEqual(result["risk_level"], "SAFE")
        self.assertEqual(result["requested_actions"], [])
        self.assertIn("USER_REPETITION", {x["code"] for x in result["evidence"]})

    def test_disclaimer_cannot_veto_real_request(self):
        result = self.ingest("I am not asking for your code. Just read me the six digits from the message.")
        codes = {x["code"] for x in result["evidence"]}
        self.assertTrue({"REQUEST_OTP", "ACTUAL_REQUEST", "DIRECTED_AT_USER", "DISCLAIMER_CONTRADICTION"} <= codes)
        self.assertEqual(result["risk_level"], "HIGH_RISK")

    def test_multiturn_pressure_accumulates_but_is_not_critical(self):
        brain = HybridBrainV1()
        brain.ingest(turn(CALLER, "I am calling from the bank", 1), NomicSignal(.55))
        brain.ingest(turn(CALLER, "This is urgent, do not call your bank", 2), NomicSignal(.55))
        result = brain.ingest(turn(CALLER, "Stay on the line", 3), NomicSignal(.55))
        self.assertEqual(result["risk_level"], "HIGH_RISK")
        self.assertNotIn("REQUEST_OTP", result["requested_actions"])

    def test_weak_pressure_expires(self):
        brain = HybridBrainV1(); brain.ingest(turn(CALLER, "urgent", 1), NomicSignal())
        for index in range(2, 12): brain.ingest(turn(CALLER, "ordinary weather discussion", index), NomicSignal())
        self.assertNotIn("URGENCY", {x["code"] for x in brain.state.evidence})

    def test_contract_is_serializable_and_localized_codes_are_stable(self):
        result = self.ingest("Spune-mi codul SMS acum", score=.2)
        self.assertEqual(result["primary_reason_code"], "OTP_REQUESTED")
        self.assertIn("ro", result["conversation_state"]["languages_seen"])
        self.assertEqual(result["nomic"]["source"], "TEST")

