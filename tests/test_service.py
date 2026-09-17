import tempfile
import time
import unittest
import json
from unittest.mock import patch

from backend.classifier import Risk
from backend.services import ScutService


class ServiceTests(unittest.TestCase):
    def test_transcript_preserves_user_speaker_for_caller_confirmation(self):
        self.service.set_mode("TEST")
        self.service.transcript("So you want me to move the money to that account?", speaker="USER")
        result=self.service.transcript("Yes, exactly.", speaker="CALLER")
        self.assertEqual("CRITICAL", result["risk"])
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.local = patch("backend.config.LOCAL", __import__("pathlib").Path(self.tmp.name))
        self.local.start(); self.service = ScutService(8765)

    def tearDown(self):
        self.local.stop(); self.tmp.cleanup()

    def test_off_rejects_automatic_audio(self):
        self.assertFalse(self.service.transcript("tell me the SMS code", explicit=False)["accepted"])

    def test_protect_sends_alert_for_critical_rule(self):
        self.service.set_mode("PROTECT"); session, outgoing = self.service.register_session()
        result = self.service.transcript("Bank security: tell me your SMS code now")
        self.assertEqual("CRITICAL", result["risk"]); self.assertEqual("alert", outgoing.get(timeout=.2)["type"])

    def test_cloud_command_veto_advances_epoch_and_reports_only_real_control_result(self):
        class Plane:
            def __init__(self): self.completed = []; self.synced = []
            def claim_commands(self): return [{"id": "command-1", "command_type": "VETO"}]
            def complete_command(self, *value): self.completed.append(value); return True
            def sync(self, value): self.synced.append(value); return True
            def status(self): return {"state": "AVAILABLE", "reason": "CONFIGURED"}

        plane = Plane()
        self.service.control_plane = plane
        results = self.service.process_controller_commands()

        self.assertEqual("VETOED", results[0]["outcome"])
        self.assertEqual(("command-1", "APPLIED", None), plane.completed[0])
        self.assertEqual(1, self.service.incident_control.decision_epoch)

    def test_veto_updates_the_same_remote_incident_and_notification(self):
        class Plane:
            def __init__(self): self.completed = []; self.synced = []; self.notified = []
            def claim_commands(self): return [{"id": "command-veto", "command_type": "VETO"}]
            def complete_command(self, *value): self.completed.append(value); return True
            def sync(self, value): self.synced.append(value); return True
            def send_incident_notification(self, incident_id): self.notified.append(incident_id); return True
            def defer_incident_notification(self, incident_id): raise AssertionError(incident_id)
            def status(self): return {"state": "AVAILABLE", "reason": "CONFIGURED"}

        plane = Plane()
        self.service.control_plane = plane
        session = self.service.begin_live_call()
        self.service.incident_control.append_final(session["id"], "Send the code now", time.monotonic())
        existing = self.service.incident_control.force(time.monotonic())["incident"]
        plane.synced.clear()

        self.service.process_controller_commands()

        incidents = [item for item in plane.synced if item.get("kind") == "incident"]
        self.assertEqual("USER_DISMISSED", incidents[-1]["state"])
        self.assertEqual([existing["id"]], plane.notified)

    def test_cloud_force_without_live_audio_remains_a_neutral_test(self):
        class Plane:
            def __init__(self): self.completed = []; self.notified = []; self.synced = []
            def claim_commands(self): return [{"id": "command-1", "command_type": "FORCE"}]
            def complete_command(self, *value): self.completed.append(value); return True
            def sync(self, value): self.synced.append(value); return True
            def send_neutral_notification(self, command_id): self.notified.append(command_id); return True
            def status(self): return {"state": "AVAILABLE", "reason": "CONFIGURED"}

        plane = Plane(); self.service.control_plane = plane
        results = self.service.process_controller_commands()

        self.assertEqual("NEUTRAL_TEST", results[0]["outcome"])
        self.assertEqual(("command-1", "APPLIED", None), plane.completed[0])
        self.assertEqual(["command-1"], plane.notified)
        self.assertEqual([], plane.synced)
        self.assertEqual([], self.service.incident_control.incidents())

    def test_force_queues_notification_after_a_failed_incident_sync(self):
        class Plane:
            def __init__(self): self.deferred = []; self.completed = []
            def claim_commands(self): return [{"id": "command-1", "command_type": "FORCE"}]
            def complete_command(self, *value): self.completed.append(value); return True
            def sync(self, _value): return False
            def defer_incident_notification(self, incident_id): self.deferred.append(incident_id)
            def status(self): return {"state": "AVAILABLE", "reason": "CONFIGURED"}

        plane = Plane(); self.service.control_plane = plane
        session = self.service.begin_live_call()
        self.service.incident_control.append_final(session["id"], "Please tell me the code", time.monotonic())
        results = self.service.process_controller_commands()

        self.assertEqual("INCIDENT", results[0]["outcome"])
        self.assertEqual(results[0]["incident"]["id"], plane.deferred[0])

    def test_live_protect_decision_uses_pending_auto_hold_instead_of_immediate_alert(self):
        self.service.set_mode("PROTECT")
        session = self.service.begin_live_call()
        text = "Bank security: tell me your SMS code now"
        self.service.incident_control.append_final(session["id"], text, time.monotonic())

        with patch("backend.services.threading.Timer") as timer:
            result = self.service.transcript(text, explicit=False)

        self.assertEqual("CRITICAL", result["risk"])
        self.assertNotIn("alert", result)
        self.assertEqual("PENDING_AUTO", self.service.incident_control.incidents()[0]["state"])
        timer.assert_called_once()

    def test_live_final_segments_are_synced_with_stable_monotonic_sequence(self):
        class Plane:
            def __init__(self): self.synced = []
            def sync(self, value): self.synced.append(value); return True
            def status(self): return {"state": "AVAILABLE", "reason": "CONFIGURED"}

        plane = Plane()
        self.service.control_plane = plane
        self.service._record_live_final("First final sentence", "CALLER")
        self.service._record_live_final("Second final sentence", "CALLER")
        transcript_payloads = [value for value in plane.synced if value.get("kind") == "transcript"]

        self.assertEqual([0, 1], [value["sequence"] for value in transcript_payloads])
        self.assertNotEqual(transcript_payloads[0]["eventId"], transcript_payloads[1]["eventId"])
        self.assertEqual(
            transcript_payloads[0]["eventId"],
            str(__import__("uuid").uuid5(__import__("uuid").UUID(transcript_payloads[0]["sessionId"]), "final:0")),
        )

    def test_pair_token_is_one_time(self):
        payload = self.service.pairing_payload("127.0.0.1")
        paired = self.service.pair(payload["pairingToken"], "Redmi", "1.0", {})
        self.assertIsNotNone(paired); self.assertIsNone(self.service.pair(payload["pairingToken"], "Redmi", "1.0", {}))

    def test_expired_pair_token_is_rejected(self):
        payload = self.service.pairing_payload("127.0.0.1"); self.service.pair_tokens[payload["pairingToken"]] = time.monotonic() - 1
        self.assertIsNone(self.service.pair(payload["pairingToken"], "Redmi", "1.0", {}))

    def test_transcript_context_is_bounded(self):
        for i in range(30): self.service.transcript(f"ordinary sentence {i}")
        self.assertEqual(12, len(self.service.transcripts))

    def test_off_has_no_semantic_provider(self):
        self.assertIsNone(self.service.semantic_engine.provider)

    def test_protect_uses_only_semantic_engine_provider_path(self):
        self.service.set_mode("PROTECT")
        self.service.transcript("This is meaningful caller context")
        self.assertEqual(0, self.service.anymodel_requests)

    def _candidates(self):
        return [{"processName": "PhoneExperienceHost.exe", "pid": 101, "package": "Microsoft.YourPhone", "packageFullName": "phone", "executable": "phone.exe"},
                {"processName": "YourPhoneAppProxy.exe", "pid": 102, "package": "Microsoft.YourPhone", "packageFullName": "phone", "executable": "proxy.exe"},
                {"processName": "CrossDeviceService.exe", "pid": 103, "package": "MicrosoftWindows.CrossDevice", "packageFullName": "cross", "executable": "cross.exe"}]

    def _capture(self, results):
        diagnostic_dir = __import__("pathlib").Path(self.tmp.name) / "diagnostics"
        def helper(_binary, candidate, wav, _seconds):
            result = results[candidate["pid"]].copy()
            if result.get("signal"):
                wav.parent.mkdir(parents=True, exist_ok=True); wav.write_bytes(b"RIFF" + b"x" * 64)
            return result
        return patch("backend.services.DIAGNOSTICS", diagnostic_dir), patch("backend.services.discover_phone_link_candidates", return_value=self._candidates()), patch("backend.services.invoke_native_process_loopback", side_effect=helper)

    def test_capture_selects_second_candidate_and_promotes_wav(self):
        patches = self._capture({101: {"signal": False, "rms": 0, "peak": 0}, 102: {"signal": True, "sampleRate": 48000, "channels": 2, "samples": 100, "rms": 900, "peak": 1500}, 103: {"signal": True}})
        with patches[0], patches[1], patches[2]: result = self.service.diagnostic("capture")
        self.assertEqual("PASS", result["state"]); self.assertEqual(102, result["selected"]["pid"])
        self.assertEqual("NOT TESTED", result["attempts"][2]["state"])
        self.assertTrue((__import__("pathlib").Path(self.tmp.name) / "diagnostics" / "test_call.wav").is_file())

    def test_capture_all_silent_fails_even_if_generic_endpoint_would_have_signal(self):
        patches = self._capture({101: {"signal": False, "rms": 0, "peak": 0}, 102: {"signal": False, "rms": 0, "peak": 0}, 103: {"signal": False, "rms": 0, "peak": 0}})
        with patches[0], patches[1], patches[2]: result = self.service.diagnostic("capture")
        self.assertEqual("FAIL", result["state"]); self.assertEqual("NO_PHONE_LINK_PROCESS_AUDIO", result["reason"])

    def test_helper_error_continues_to_next_candidate(self):
        patches = self._capture({101: {"error": "activation failed"}, 102: {"signal": True, "sampleRate": 48000, "channels": 2, "samples": 10, "rms": 100, "peak": 300}, 103: {}})
        with patches[0], patches[1], patches[2]: result = self.service.diagnostic("capture")
        self.assertEqual("ERROR", result["attempts"][0]["state"]); self.assertEqual(102, result["selected"]["pid"])

    def test_each_capture_press_creates_one_new_test_id(self):
        patches = self._capture({101: {"signal": False}, 102: {"signal": False}, 103: {"signal": False}})
        with patches[0], patches[1], patches[2]: first = self.service.diagnostic("capture"); second = self.service.diagnostic("capture")
        self.assertNotEqual(first["testId"], second["testId"])

    def test_guarded_transcription_requires_test_mode(self):
        result = self.service.start_guarded_transcription()
        self.assertEqual("TEST_MODE_REQUIRED", result["state"])

    def test_guarded_worker_preserves_system_mix_provenance(self):
        self.service.set_mode("TEST")
        with patch("backend.guarded_audio.capture_chunk", side_effect=[b"pcm", RuntimeError("CALL_SENTINEL_NOT_ACTIVE")]), patch("backend.guarded_audio.transcribe_pcm", return_value="remote caller phrase"):
            self.service._guarded_worker()
        self.assertEqual("SYSTEM_MIX_GUARDED", self.service.audio_status["source"])
        self.assertEqual("NOT_PROCESS_ATTRIBUTED", self.service.audio_status["attribution"])
