import unittest

from scripts.tail_aware_encoder import dangerous_action_target


class ChampionshipTargetTests(unittest.TestCase):
    def test_actual_directed_action_is_positive(self):
        self.assertEqual(dangerous_action_target({"labels": ["ACTUAL_REQUEST", "DIRECTED_AT_USER", "CREDENTIAL_DISCLOSURE"]}), 1)

    def test_quoted_negated_and_hypothetical_actions_are_negative(self):
        for exclusion in ("QUOTATION", "NEGATION", "HYPOTHETICAL"):
            self.assertEqual(dangerous_action_target({"labels": ["ACTUAL_REQUEST", "DIRECTED_AT_USER", exclusion]}), 0)

    def test_manipulation_only_is_not_an_action(self):
        self.assertEqual(dangerous_action_target({"labels": ["ACTUAL_REQUEST", "DIRECTED_AT_USER", "URGENCY_OR_TIME_PRESSURE"]}), 0)


if __name__ == "__main__":
    unittest.main()
