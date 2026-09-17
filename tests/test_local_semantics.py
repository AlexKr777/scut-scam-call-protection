import unittest

from backend.classifier import Risk, classify_local
from backend.realtime_pipeline import CALLER, USER, Utterance


class LocalSemanticTests(unittest.TestCase):
    def turn(self, speaker, text, ident="u"):
        return Utterance(ident, speaker, text, 0, 1)

    def test_protective_credential_advice_does_not_create_active_fact(self):
        from backend.local_semantics import LocalSemanticAnalyzer
        from backend.semantic_ontology import DialogueMemory
        facts = LocalSemanticAnalyzer().analyze(self.turn(CALLER, "Never share the SMS confirmation number with anyone."), DialogueMemory())
        self.assertFalse(any(f.is_active_dangerous for f in facts))

    def test_credential_euphemism_is_critical_without_identity(self):
        self.assertEqual(Risk.CRITICAL, classify_local("I do not need your code. Just read the six digits that arrived in the message.").risk)

    def test_quoted_request_is_safe_but_following_directive_is_not(self):
        self.assertEqual(Risk.SAFE, classify_local("Scammers say: 'move funds to a safe account'.").risk)
        self.assertEqual(Risk.CRITICAL, classify_local("Scammers say move funds. Now move them to the details I dictate.").risk)

    def test_conditional_current_directive_is_dangerous(self):
        self.assertEqual(Risk.CRITICAL, classify_local("If you want to cancel the operation, enter the code on the page I sent.").risk)

    def test_remote_session_request_does_not_require_brand_name(self):
        self.assertEqual(Risk.CRITICAL, classify_local("Install the support application, open it, then tell me the connection ID.").risk)

    def test_mixed_language_money_request_and_secrecy_is_critical(self):
        self.assertEqual(Risk.CRITICAL, classify_local("Transferați banii acum, никому пока nu spuneți.").risk)

    def test_russian_credential_request_is_critical(self):
        self.assertEqual(Risk.CRITICAL, classify_local("Сообщите код из SMS сейчас.").risk)

    def test_balance_placement_euphemism_to_dictated_details_is_critical(self):
        self.assertEqual(Risk.CRITICAL, classify_local("Temporarily place the balance at the details I dictate and do not verify it.").risk)

    def test_caller_yes_confirms_prior_user_transfer_proposition(self):
        from backend.local_semantics import LocalSemanticAnalyzer
        from backend.semantic_ontology import DialogueMemory, SemanticAction
        analyzer, memory = LocalSemanticAnalyzer(), DialogueMemory()
        user = self.turn(USER, "So you want me to move the money to that account?", "user")
        memory.ingest(user, analyzer.analyze(user, memory))
        facts = analyzer.analyze(self.turn(CALLER, "Yes, exactly.", "caller"), memory)
        self.assertIn(SemanticAction.TRANSFER_MONEY, {fact.action for fact in facts})
