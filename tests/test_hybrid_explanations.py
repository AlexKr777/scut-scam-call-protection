import unittest
from backend.hybrid_explanations import TEMPLATES, explain

class HybridExplanationTests(unittest.TestCase):
    def test_required_reason_codes_have_all_three_locales(self):
        required = {"OTP_REQUESTED", "MONEY_TRANSFER_REQUESTED", "REMOTE_ACCESS_REQUESTED", "REQUEST_OPEN_LINK", "REQUEST_CRYPTO_TRANSFER", "REQUEST_CASH_TO_COURIER", "IDENTITY_BANK_CLAIMED", "URGENCY_DETECTED", "SECRECY_REQUESTED", "KEEP_CALL_ACTIVE_DETECTED", "VERIFYING_DISCOURAGED", "PROTECTIVE_ADVICE_DETECTED"}
        for language in ("ru", "ro", "en"): self.assertTrue(required <= set(TEMPLATES[language]))
    def test_explanations_are_deterministic_and_fallback_is_safe(self):
        self.assertEqual(explain(["OTP_REQUESTED"], "ro"), ["Interlocutorul a solicitat un cod de confirmare."])
        self.assertEqual(explain(["UNKNOWN"], "ru"), ["Social-engineering indicators were detected."])
