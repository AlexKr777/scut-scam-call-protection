import unittest
from backend.realtime_pipeline import CALLER, Utterance
from backend.semantic_ontology import DialogueMemory, SemanticAction


class FakeNli:
    def __init__(self): self.calls=[]
    def verify_pairs(self, pairs):
        from backend.neural_nli import NliLabel, NliResult
        self.calls.append(pairs)
        return [NliResult(NliLabel.ENTAILMENT, .95, .02, .03) for _ in pairs]


class NeuralSemanticTests(unittest.TestCase):
    def test_core_discovery_runs_without_deterministic_fact(self):
        from backend.neural_semantics import NeuralSemanticAnalyzer
        runtime=FakeNli(); facts=NeuralSemanticAnalyzer(runtime).analyze(Utterance("x",CALLER,"An unrelated paraphrase.",0,1), DialogueMemory(), [])
        self.assertTrue(runtime.calls)
        self.assertGreaterEqual(len(runtime.calls[0]), 8)

    def test_entailed_core_money_hypothesis_becomes_typed_fact(self):
        from backend.neural_semantics import NeuralSemanticAnalyzer
        facts=NeuralSemanticAnalyzer(FakeNli()).analyze(Utterance("x",CALLER,"An unrelated paraphrase.",0,1), DialogueMemory(), [])
        self.assertIn(SemanticAction.TRANSFER_MONEY, {fact.action for fact in facts})

    def test_quoted_deterministic_scope_prevents_neural_dangerous_promotion(self):
        from backend.neural_semantics import NeuralSemanticAnalyzer
        from backend.semantic_ontology import Polarity, SemanticFact, SpeechAct
        quoted=SemanticFact(SemanticAction.TRANSFER_MONEY,.9,CALLER,CALLER,SpeechAct.QUOTATION,Polarity.QUOTED,("x",))
        facts=NeuralSemanticAnalyzer(FakeNli()).analyze(Utterance("x",CALLER,"Scammers say move money.",0,1), DialogueMemory(), [quoted])
        self.assertFalse(any(fact.is_active_dangerous for fact in facts))
