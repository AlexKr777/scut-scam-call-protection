import unittest
from backend.classifier import Risk, classify_local


class ClassifierTests(unittest.TestCase):
    def test_active_sensitive_request_is_critical(self):
        self.assertEqual(Risk.CRITICAL, classify_local("I am from bank security. Tell me the SMS code now.").risk)

    def test_russian_active_request_is_critical(self):
        self.assertEqual(Risk.CRITICAL, classify_local("Я из службы безопасности банка, сообщите код из СМС").risk)

    def test_protective_advice_is_safe(self):
        self.assertEqual(Risk.SAFE, classify_local("Never share an SMS code with anyone, even the bank.").risk)

    def test_romanian_negation_is_safe(self):
        self.assertEqual(Risk.SAFE, classify_local("Nu comunicați nimănui codul din SMS.").risk)

    def test_keyword_alone_is_not_critical(self):
        self.assertEqual(Risk.SAFE, classify_local("We discussed a password manager yesterday.").risk)
