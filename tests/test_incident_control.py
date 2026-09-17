import unittest

from backend.incident_control import IncidentCoordinator


class IncidentCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = IncidentCoordinator(auto_hold_seconds=1.5)

    def test_force_reuses_one_incident_for_repeated_presses_in_dedup_window(self):
        self.coordinator.start_session("session-1", started_at=100.0)
        self.coordinator.append_final("session-1", "Tell me the code", ended_at=105.0)

        first = self.coordinator.force(now=106.0)
        repeated = self.coordinator.force(now=109.0)

        self.assertEqual("INCIDENT", first["outcome"])
        self.assertEqual(first["incident"]["id"], repeated["incident"]["id"])
        self.assertEqual("PENDING_FORCE", repeated["incident"]["state"])
        self.assertEqual(["Tell me the code"], repeated["incident"]["transcript"])

    def test_force_without_an_active_call_is_neutral_and_creates_no_incident(self):
        result = self.coordinator.force(now=100.0)

        self.assertEqual({"outcome": "NEUTRAL_TEST"}, result)
        self.assertEqual([], self.coordinator.incidents())

    def test_veto_advances_epoch_and_rejects_a_stale_automatic_decision(self):
        self.coordinator.start_session("session-1", started_at=100.0)
        self.coordinator.append_final("session-1", "bank security", ended_at=105.0)
        pending = self.coordinator.queue_automatic("session-1", decision_epoch=0, now=106.0)

        veto = self.coordinator.veto(now=107.0)
        stale = self.coordinator.confirm_automatic(pending["incident"]["id"], decision_epoch=0, now=108.0)

        self.assertEqual(1, veto["decisionEpoch"])
        self.assertEqual("STALE_DECISION", stale["outcome"])
        self.assertEqual("USER_DISMISSED", stale["incident"]["state"])
        self.assertEqual(1, stale["incident"]["decisionEpoch"])

    def test_force_and_automatic_evidence_merge_into_the_current_session_incident(self):
        self.coordinator.start_session("session-1", started_at=100.0)
        self.coordinator.append_final("session-1", "Please share your OTP", ended_at=105.0)
        manual = self.coordinator.force(now=106.0)

        automatic = self.coordinator.queue_automatic("session-1", decision_epoch=0, now=107.0)

        self.assertEqual(manual["incident"]["id"], automatic["incident"]["id"])
        self.assertEqual("PENDING_AUTO", automatic["incident"]["state"])


if __name__ == "__main__":
    unittest.main()
