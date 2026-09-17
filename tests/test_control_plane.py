import os
import tempfile
import unittest
from unittest.mock import patch

from backend.control_plane import ControlPlaneClient, ControlPlaneConfig


class ControlPlaneTests(unittest.TestCase):
    def test_neutral_push_uses_send_fcm_without_incident_and_retries_after_outage(self):
        config = ControlPlaneConfig("https://example.supabase.co", "safe-exe-token-at-least-24-characters")
        calls = []
        offline = True

        def transport(url, payload, headers):
            calls.append((url, payload))
            if offline:
                raise OSError("offline")
            return {"kind": "NEUTRAL_TEST", "messageId": "firebase-response"}

        with tempfile.TemporaryDirectory() as directory, patch("backend.config.LOCAL", __import__("pathlib").Path(directory)):
            client = ControlPlaneClient(config, transport=transport)
            self.assertFalse(client.send_neutral_notification("command-1"))
            offline = False
            self.assertEqual(1, client.flush_outbox())
            self.assertEqual(0, client.flush_outbox())
        self.assertEqual([("https://example.supabase.co/functions/v1/send-fcm", {"kind": "NEUTRAL_TEST", "commandId": "command-1"})] * 2, calls)

    def test_missing_configuration_is_explicitly_unavailable(self):
        # The production checkout may have a real, gitignored control-plane
        # file. Keep this absence-contract test independent of that machine.
        with tempfile.TemporaryDirectory() as directory, patch("backend.config.LOCAL", __import__("pathlib").Path(directory)), patch.dict(os.environ, {}, clear=True):
            client = ControlPlaneClient(ControlPlaneConfig.from_environment())

        self.assertEqual("UNAVAILABLE", client.status()["state"])
        self.assertEqual([], client.claim_commands())

    def test_restricted_local_configuration_is_used_when_environment_is_absent(self):
        with tempfile.TemporaryDirectory() as directory, patch("backend.config.LOCAL", __import__("pathlib").Path(directory)), patch.dict(os.environ, {}, clear=True):
            from backend.config import atomic_json
            atomic_json("control_plane.json", {"url": "https://example.supabase.co", "exeToken": "safe-exe-token-at-least-24-characters"}, restrict=True)
            config = ControlPlaneConfig.from_environment()

        self.assertTrue(config.configured)

    def test_claims_leased_commands_only_when_complete_configuration_exists(self):
        config = ControlPlaneConfig("https://example.supabase.co", "safe-exe-token-at-least-24-characters")
        calls = []

        def transport(url, payload, headers):
            calls.append((url, payload, headers))
            return {"commands": [{"id": "command-1", "command_type": "VETO"}]}

        commands = ControlPlaneClient(config, transport=transport).claim_commands()

        self.assertEqual("VETO", commands[0]["command_type"])
        self.assertEqual("https://example.supabase.co/functions/v1/exe-commands", calls[0][0])
        self.assertEqual("safe-exe-token-at-least-24-characters", calls[0][2]["x-scut-exe-token"])

    def test_transport_failure_never_claims_a_command_or_reports_delivery(self):
        config = ControlPlaneConfig("https://example.supabase.co", "safe-exe-token-at-least-24-characters")

        def failing_transport(_url, _payload, _headers):
            raise OSError("offline")

        client = ControlPlaneClient(config, transport=failing_transport)

        self.assertEqual([], client.claim_commands())
        self.assertEqual("DEGRADED", client.status()["state"])
        self.assertFalse(client.send_incident_notification("00000000-0000-4000-8000-000000000000"))

    def test_release_uses_only_the_authenticated_exe_boundary(self):
        config = ControlPlaneConfig("https://example.supabase.co", "safe-exe-token-at-least-24-characters")
        calls = []
        client = ControlPlaneClient(config, transport=lambda url, payload, headers: calls.append((url, payload, headers)) or {"state": "NO_CONTROLLER", "released": True})

        self.assertEqual({"state": "NO_CONTROLLER", "released": True}, client.release_controller())
        self.assertEqual("https://example.supabase.co/functions/v1/release-controller", calls[0][0])
        self.assertEqual({}, calls[0][1])
        self.assertEqual("safe-exe-token-at-least-24-characters", calls[0][2]["x-scut-exe-token"])

    def test_history_operations_use_only_the_authenticated_exe_boundary(self):
        config = ControlPlaneConfig("https://example.supabase.co", "safe-exe-token-at-least-24-characters")
        calls = []

        def transport(url, payload, headers):
            calls.append((url.rsplit("/", 1)[-1], payload, headers))
            if url.endswith("history-list"):
                return {"conversations": [], "nextCursor": None}
            if url.endswith("conversation-detail"):
                return {"conversation": {"id": payload["conversationId"], "segments": []}}
            if url.endswith("alerts-list"):
                return {"alerts": [], "nextCursor": None}
            return {"deleted": True}

        client = ControlPlaneClient(config, transport=transport)
        conversation_id = "00000000-0000-4000-8000-000000000001"

        self.assertEqual([], client.list_history()["conversations"])
        self.assertEqual(conversation_id, client.conversation_detail(conversation_id)["conversation"]["id"])
        self.assertEqual([], client.list_alerts()["alerts"])
        self.assertTrue(client.delete_conversation(conversation_id))
        self.assertEqual(
            ["history-list", "conversation-detail", "alerts-list", "conversation-delete"],
            [call[0] for call in calls],
        )
        self.assertTrue(all(call[2]["x-scut-exe-token"] == config.exe_token for call in calls))

    def test_configured_outbox_retries_the_same_incident_payload_after_an_outage(self):
        config = ControlPlaneConfig("https://example.supabase.co", "safe-exe-token-at-least-24-characters")
        attempt = {"offline": True}; observed = []

        def transport(_url, payload, _headers):
            if attempt["offline"]: raise OSError("offline")
            observed.append(payload); return {"synced": "incident"}

        with tempfile.TemporaryDirectory() as directory, patch("backend.config.LOCAL", __import__("pathlib").Path(directory)):
            client = ControlPlaneClient(config, transport=transport)
            payload = {"kind": "incident", "id": "00000000-0000-4000-8000-000000000000"}
            self.assertFalse(client.sync(payload))
            attempt["offline"] = False
            self.assertEqual(1, client.flush_outbox())

        self.assertEqual(payload, observed[0])


if __name__ == "__main__":
    unittest.main()
