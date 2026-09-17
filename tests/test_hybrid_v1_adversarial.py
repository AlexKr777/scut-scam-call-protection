"""DEVELOPMENT_ONLY jury suite; authored scenario families, never OOF transcripts."""
from __future__ import annotations
import unittest
from backend.hybrid_v1 import HybridBrainV1, NomicSignal
from backend.realtime_pipeline import CALLER, USER, Utterance

def run_case(turns, score=.15):
    brain = HybridBrainV1(); result = None
    for number, (speaker, text) in enumerate(turns, 1): result = brain.ingest(Utterance(str(number), speaker, text, 0, 0), NomicSignal(score, source="JURY_DEVELOPMENT_ONLY"))
    return result

class HybridV1AdversarialTests(unittest.TestCase):
    # 32 separate, authored conversation cases: direct, indirect, ASR-like,
    # multilingual, mixed-language, protective, and legitimate controls.
    dangerous = (
        ("en_direct_otp", [(CALLER,"Tell me the SMS verification code now")], "REQUEST_OTP"),
        ("en_disguised_otp", [(CALLER,"I only need you to read the six digits that arrived")], "REQUEST_OTP"),
        ("en_safe_account", [(CALLER,"Move your money to the safe account")], "REQUEST_SAFE_ACCOUNT_TRANSFER"),
        ("en_money", [(CALLER,"Send money to these bank details")], "REQUEST_MONEY_TRANSFER"),
        ("en_remote", [(CALLER,"Install AnyDesk and allow remote access")], "REQUEST_REMOTE_ACCESS"),
        ("en_link", [(CALLER,"Open the link I sent")], "REQUEST_OPEN_LINK"),
        ("en_qr", [(CALLER,"Scan the QR code now")], "REQUEST_SCAN_QR"),
        ("en_crypto", [(CALLER,"Send crypto to this wallet")], "REQUEST_CRYPTO_TRANSFER"),
        ("en_gift", [(CALLER,"Send a gift card code")], "REQUEST_GIFT_CARD"),
        ("en_courier", [(CALLER,"Give cash to the courier")], "REQUEST_CASH_TO_COURIER"),
        ("en_family", [(CALLER,"Your sister had an accident, send money now")], "REQUEST_MONEY_TRANSFER"),
        ("ru_otp", [(CALLER,"Назовите код из СМС")], "REQUEST_OTP"),
        ("ru_remote", [(CALLER,"Установите AnyDesk и разрешите удаленный доступ")], "REQUEST_REMOTE_ACCESS"),
        ("ro_otp", [(CALLER,"Spuneți-mi codul SMS acum")], "REQUEST_OTP"),
        ("ro_money", [(CALLER,"Transferați banii în contul sigur")], "REQUEST_SAFE_ACCOUNT_TRANSFER"),
        ("mixed_ro_en", [(CALLER,"Spune codul from SMS now")], "REQUEST_OTP"),
        ("mixed_ru_en", [(CALLER,"Назовите verification code now")], "REQUEST_OTP"),
        ("mixed_ru_ro", [(CALLER,"Переведите banii в безопасный счет")], "REQUEST_MONEY_TRANSFER"),
        ("asr_no_punctuation", [(CALLER,"tell me sms code now")], "REQUEST_OTP"),
        ("fake_disclaimer_otp", [(CALLER,"I am not asking for the code just read me the six digits")], "REQUEST_OTP"),
        ("fake_disclaimer_money", [(CALLER,"We do not ask customers to transfer money move it to the reserve account")], "REQUEST_SAFE_ACCOUNT_TRANSFER"),
    )
    safe = (
        ("en_protective", [(CALLER,"Do not give anyone the code")]),
        ("ro_protective", [(CALLER,"Nu comunicați nimănui codul")]),
        ("ru_protective", [(CALLER,"Никому не сообщайте код из СМС")]),
        ("quotation", [(CALLER,"Scammers say give me the code; this is training")]),
        ("hypothetical", [(CALLER,"If someone asks for your code, hang up")]),
        ("user_repetition", [(USER,"Are you asking me for the SMS code?")]),
        ("legitimate_bank_warning", [(CALLER,"Our bank will never request your password on a call")]),
        ("legitimate_support", [(CALLER,"Support can help reset your printer tomorrow")]),
        ("legitimate_delivery", [(CALLER,"Your delivery arrives between ten and noon")]),
        ("authority_urgency_only", [(CALLER,"I am police and this is urgent")]),
    )
    def test_dangerous_cases_have_action_evidence_and_severe_alert(self):
        for name, turns, code in self.dangerous:
            with self.subTest(name=name):
                result = run_case(turns); codes = {item["code"] for item in result["evidence"]}
                self.assertIn(code, codes); self.assertIn(result["risk_level"], {"HIGH_RISK", "CRITICAL"}); self.assertTrue(result["alert_recommended"]); self.assertTrue(result["explanation"]["reason_codes"])
    def test_safe_cases_have_no_severe_alert(self):
        for name, turns in self.safe:
            with self.subTest(name=name):
                result = run_case(turns, .55 if name == "multiturn_pressure" else .15)
                self.assertNotIn(result["risk_level"], {"HIGH_RISK", "CRITICAL"}); self.assertFalse(result["alert_recommended"])
    def test_fake_disclaimers_are_explicitly_contradictory(self):
        for name, turns, _ in self.dangerous[-2:]:
            with self.subTest(name=name): self.assertIn("DISCLAIMER_CONTRADICTION", {x["code"] for x in run_case(turns)["evidence"]})
    def test_multiple_manipulation_signals_escalate_only_with_moderate_nomic(self):
        turns = [(CALLER,"I am calling from the bank"),(CALLER,"This is urgent, stay on the line"),(CALLER,"Do not call your bank")]
        result = run_case(turns, .55)
        self.assertEqual(result["risk_level"], "HIGH_RISK")
        self.assertNotIn("REQUEST_OTP", result["requested_actions"])
