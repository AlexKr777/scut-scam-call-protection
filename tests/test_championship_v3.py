import unittest

import numpy as np


class ChampionshipV3Tests(unittest.TestCase):
    def test_constrained_threshold_search_rejects_gate_failures(self):
        from scripts.run_brain_championship_v3 import constrained_threshold_search

        rows = [
            {"fold": 0, "language": "en", "kind": "dangerous"},
            {"fold": 0, "language": "en", "kind": "dangerous"},
            {"fold": 0, "language": "en", "kind": "dangerous"},
            {"fold": 0, "language": "en", "kind": "dangerous"},
            {"fold": 0, "language": "en", "kind": "dangerous"},
            {"fold": 1, "language": "ru", "kind": "legitimate"},
            {"fold": 1, "language": "ru", "kind": "legitimate"},
            {"fold": 1, "language": "ru", "kind": "legitimate"},
            {"fold": 1, "language": "ru", "kind": "legitimate"},
            {"fold": 1, "language": "ru", "kind": "legitimate"},
        ]
        result = constrained_threshold_search(
            np.array([.9, .9, .9, .9, .9, .9, .9, .9, .9, .9]),
            np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0]),
            rows,
            thresholds=(.5, .95),
        )
        self.assertIsNone(result["chosen"])
        self.assertFalse(result["evaluations"][0]["qualification"]["qualified"])

    def test_sampling_weights_only_use_training_rows(self):
        from scripts.run_brain_championship_v3 import balanced_sample_weights

        rows = [
            {"kind": "dangerous", "language": "en"},
            {"kind": "dangerous", "language": "en"},
            {"kind": "dangerous", "language": "ru"},
            {"kind": "legitimate", "language": "en"},
        ]
        weights, distribution = balanced_sample_weights(rows)
        self.assertEqual(len(weights), len(rows))
        self.assertGreater(weights[2], weights[0])
        self.assertEqual(distribution["input_count"], 4)

    def test_precision_policy_prefers_bf16_when_supported(self):
        from scripts.run_brain_championship_v3 import precision_mode

        self.assertEqual(precision_mode(True), "bf16")
        self.assertEqual(precision_mode(False), "fp16")

    def test_worst_fold_gate_is_not_overridden_by_aggregate_qualification(self):
        from scripts.run_brain_championship_v3 import all_frozen_gates_pass

        self.assertFalse(all_frozen_gates_pass({"qualified": True, "worst_fold_recall": .84}))
        self.assertTrue(all_frozen_gates_pass({"qualified": True, "worst_fold_recall": .85}))

    def test_hard_mining_weights_only_misclassified_train_side_examples(self):
        from scripts.run_brain_championship_v3 import hard_mining_weights

        rows = [
            {"id": "hard-positive", "kind": "dangerous"},
            {"id": "hard-negative", "kind": "legitimate"},
            {"id": "easy", "kind": "dangerous"},
        ]
        weights, selected = hard_mining_weights(rows, {"hard-positive": .1, "hard-negative": .9, "easy": .9})
        self.assertEqual(selected["hard_positive_ids"], ["hard-positive"])
        self.assertEqual(selected["hard_negative_ids"], ["hard-negative"])
        self.assertGreater(weights[0], weights[2])
