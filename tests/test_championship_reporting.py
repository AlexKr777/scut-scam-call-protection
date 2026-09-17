import unittest
import numpy as np

from scripts.championship_reporting import (
    benchmark_finalists,
    build_champion_manifest,
    build_oof_breakdowns,
    build_screening_summary,
)
from scripts.run_brain_championship import write_deployment_cost_report


class ReportingTests(unittest.TestCase):
    def test_deployment_report_contains_proxy_cpu_and_required_caveat(self):
        report = benchmark_finalists([{
            "id": "e5_base-top_2", "total_parameters": 10,
            "cpu_proxy_ms": {"short": 1.0, "medium": 2.0, "long_384": 3.0},
        }])

        self.assertEqual(set(report["cpu_proxy_ms"]), {"short", "medium", "long_384"})
        self.assertEqual(report["cpu_proxy_ms"]["medium"], 2.0)
        self.assertIn("ACTUAL DEMO LAPTOP", report["caveat"])

    def test_screening_summary_enumerates_every_expected_fit_state(self):
        expected = [{"fit_id": f"fit-{index}"} for index in range(24)]
        report = build_screening_summary(
            expected,
            [{"fit_id": "fit-0", "status": "COMPLETED"}],
            [{"id": "winner", "rank": 1, "qualification": {"qualified": True}}],
            important_labels=["CREDENTIAL_DISCLOSURE"],
        )

        self.assertEqual(len(report["expected_fits"]), 24)
        self.assertEqual(report["fit_states"]["COMPLETED"], ["fit-0"])
        self.assertEqual(report["fit_states"]["PENDING"], [f"fit-{index}" for index in range(1, 24)])
        self.assertEqual(report["important_labels"], ["CREDENTIAL_DISCLOSURE"])

    def test_oof_breakdowns_include_language_asr_clean_and_minimal_pairs(self):
        report = build_oof_breakdowns(
            action_probabilities=np.array([.9, .1, .8, .2]),
            action_targets=np.array([1, 0, 1, 0]),
            semantic_probabilities=np.array([[.9], [.1], [.8], [.2]]),
            semantic_targets=np.array([[1], [0], [1], [0]]),
            labels=["CREDENTIAL_DISCLOSURE"],
            rows=[
                {"id": "a", "language": "en", "variant_type": "clean", "minimal_pair_id": "p1"},
                {"id": "b", "language": "en", "variant_type": "asr", "minimal_pair_id": "p1"},
                {"id": "c", "language": "ru", "variant_type": "clean"},
                {"id": "d", "language": "ru", "variant_type": "asr"},
            ],
            action_threshold=.5,
            semantic_thresholds={"__global__": .5, "CREDENTIAL_DISCLOSURE": .5},
        )

        self.assertEqual(set(report), {"language", "asr_vs_clean", "minimal_pairs", "important_labels"})
        self.assertEqual(report["language"]["en"]["action"]["tp"], 1)
        self.assertEqual(report["asr_vs_clean"]["clean"]["action"]["tn"], 0)
        self.assertEqual(report["minimal_pairs"]["p1"]["record_ids"], ["a", "b"])

    def test_champion_manifest_records_runner_up_loss_and_validation_zero_support(self):
        report = build_champion_manifest(
            {"id": "winner", "checkpoint_sha256": "abc", "thresholds": {"action": .5}},
            {"id": "runner", "lexicographic_tuple": [True, .7]},
            {"semantic": {"per_label": {"CREDENTIAL_DISCLOSURE": {"support": 0}}}},
        )

        self.assertEqual(report["runner_up"]["loss_reason"], "lower safety-first lexicographic ranking")
        self.assertEqual(
            report["validation"]["semantic"]["per_label"]["CREDENTIAL_DISCLOSURE"]["status"],
            "UNASSESSED_ON_VALIDATION",
        )
        self.assertEqual(report["checkpoint_sha256"], "abc")

    def test_runner_writes_deployment_cost_artifact_for_finalists(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temporary:
            path = write_deployment_cost_report(
                Path(temporary),
                [{"id": "winner", "cpu_proxy_ms": {"short": 1, "medium": 2, "long_384": 3}}],
            )
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["finalists"][0]["id"], "winner")
        self.assertIn("ACTUAL DEMO LAPTOP", saved["caveat"])


if __name__ == '__main__':
    unittest.main()
