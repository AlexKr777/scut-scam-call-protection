import unittest


class SemanticBenchmarkTests(unittest.TestCase):
    def test_jury_holdout_is_excluded_and_augmentation_is_deterministic(self):
        from backend.semantic_dataset import augment_case, base_cases, jury_red_team_cases, split_cases
        base, holdout = base_cases(), jury_red_team_cases()
        self.assertEqual(augment_case(base[0]), augment_case(base[0]))
        split = split_cases(base)
        self.assertTrue({case.id for case in holdout}.isdisjoint({case.id for cases in split.values() for case in cases}))

    def test_benchmark_exposes_quality_and_language_metrics(self):
        from backend.semantic_benchmark import run_benchmark
        from backend.semantic_dataset import base_cases, jury_red_team_cases
        report = run_benchmark(base_cases(), jury_red_team_cases())
        for key in ("criticalScamRecall", "protectiveFalseCriticalRate", "juryRedTeamRecall", "languages", "latencyMs", "readiness"):
            self.assertIn(key, report)

    def test_development_corpus_is_large_and_has_no_cross_group_duplicates(self):
        from backend.semantic_dataset import development_cases, normalized_leakage, split_cases
        cases=development_cases()
        self.assertGreaterEqual(len(cases),250)
        self.assertFalse(normalized_leakage(cases))
        groups={group for split in split_cases(cases).values() for group in {case.group for case in split}}
        self.assertGreaterEqual(len(groups),25)
