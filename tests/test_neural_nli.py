import os
import unittest
from pathlib import Path


MODEL_ROOT = Path(__file__).resolve().parents[1] / ".local" / "models" / "mdeberta-v3-base-mnli-xnli"
RUN_NLI_INTEGRATION_TESTS = os.environ.get("SCUT_RUN_NLI_INTEGRATION_TESTS") == "1"
NLI_INTEGRATION_REQUIREMENT = (
    "integration test: set SCUT_RUN_NLI_INTEGRATION_TESTS=1 and provision "
    ".local/models/mdeberta-v3-base-mnli-xnli/{config.json,tokenizer.json,model_quantized.onnx}"
)


class LocalNliRuntimeTests(unittest.TestCase):
    def test_label_mapping_comes_from_model_config_not_numeric_assumptions(self):
        from backend.neural_nli import NliLabel, label_mapping_from_config
        mapping = label_mapping_from_config({"id2label": {"0": "neutral", "1": "contradiction", "2": "entailment"}})
        self.assertEqual(NliLabel.ENTAILMENT, mapping[2])
        self.assertEqual(NliLabel.CONTRADICTION, mapping[1])
        self.assertEqual(NliLabel.UNKNOWN, mapping[0])

    def test_unknown_label_configuration_is_rejected(self):
        from backend.neural_nli import label_mapping_from_config
        with self.assertRaises(ValueError):
            label_mapping_from_config({"id2label": {"0": "LABEL_0"}})

    @unittest.skipUnless(RUN_NLI_INTEGRATION_TESTS, NLI_INTEGRATION_REQUIREMENT)
    def test_downloaded_model_maps_known_entailment_contradiction_and_neutral(self):
        from backend.neural_nli import LocalNliRuntime, NliLabel
        runtime=LocalNliRuntime(MODEL_ROOT)
        results=runtime.verify_pairs([
            ("A person is reading a book.", "A person is reading."),
            ("A person is reading a book.", "Nobody is reading."),
            ("A person is reading a book.", "The book is red."),
        ])
        self.assertEqual([NliLabel.ENTAILMENT,NliLabel.CONTRADICTION,NliLabel.UNKNOWN],[result.label for result in results])
