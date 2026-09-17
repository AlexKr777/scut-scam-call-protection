import unittest

import numpy as np

from scripts.championship_metrics import (
    rank_candidates, safety_qualification, select_action_threshold,
    select_global_semantic_threshold, select_median_seed,
)


class ChampionshipMetricsTests(unittest.TestCase):
    def test_action_threshold_prioritizes_safety_gate(self):
        probabilities = np.array([.9, .8, .7, .6, .1, .1, .1, .1, .1, .1])
        truth = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
        rows = [{"kind": "dangerous"}] * 4 + [{"kind": "protective"}] * 6
        chosen = select_action_threshold(probabilities, truth, rows)
        self.assertTrue(chosen["qualified"])
        self.assertEqual(chosen["threshold"], .6)

    def test_global_threshold_breaks_ties_by_higher_threshold(self):
        probs = np.array([[.6], [.6], [.6], [.6], [.6], [.4]])
        truth = np.array([[1], [1], [1], [1], [1], [0]])
        self.assertEqual(select_global_semantic_threshold(probs, truth, ["x"]), .6)

    def test_catastrophic_and_insufficient_support_are_explicit(self):
        rows = ([{"kind": "dangerous", "language": "ru", "fold": 0}] * 5 +
                [{"kind": "protective", "language": "en", "fold": 1}] * 2)
        result = safety_qualification(np.array([0, 0, 0, 0, 0, 0, 0]), np.array([1, 1, 1, 1, 1, 0, 0]), rows)
        self.assertFalse(result["qualified"])
        self.assertTrue(result["catastrophic_folds"])
        self.assertEqual(result["languages"]["en"]["status"], "INSUFFICIENT_SUPPORT")

    def test_lexicographic_safety_beats_semantic_score(self):
        ranked = rank_candidates([
            {"id": "unsafe", "qualification": {"qualified": False}, "semantic_macro_f1": .99},
            {"id": "safe", "qualification": {"qualified": True, "worst_fold_recall": .85, "overall_recall": .85, "safe_fp_max": .1, "precision": .7}, "semantic_macro_f1": .2, "semantic_micro_f1": .2},
        ])
        self.assertEqual(ranked[0]["id"], "safe")

    def test_seed_selection_uses_middle_safety_rank(self):
        result = select_median_seed([
            {"seed": 17, "qualification": {"qualified": True, "worst_fold_recall": .7, "overall_recall": .7, "safe_fp_max": .1, "precision": .5}},
            {"seed": 29, "qualification": {"qualified": True, "worst_fold_recall": .8, "overall_recall": .8, "safe_fp_max": .1, "precision": .5}},
            {"seed": 43, "qualification": {"qualified": True, "worst_fold_recall": .9, "overall_recall": .9, "safe_fp_max": .1, "precision": .5}},
        ])
        self.assertEqual(result["seed"], 29)


if __name__ == "__main__":
    unittest.main()
