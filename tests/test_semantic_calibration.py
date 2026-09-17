import unittest


class CalibrationTests(unittest.TestCase):
    def test_threshold_is_selected_from_validation_examples(self):
        from backend.semantic_calibration import threshold_from_validation
        threshold=threshold_from_validation([(0.90,True),(0.80,True),(0.45,False),(0.20,False)])
        self.assertGreater(threshold,.45)
        self.assertLessEqual(threshold,.80)
