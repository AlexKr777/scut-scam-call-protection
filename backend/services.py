import hashlib
import json
import platform
import queue
import shutil
import socket
import subprocess
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from .classifier import Decision, Risk, classify_local
from .config import machine_config, new_secret, read_json, save_machine_config
from .control_plane import ControlPlaneClient
from .incident_control import IncidentCoordinator
from .constants import DIAGNOSTICS, HEARTBEAT_TTL_SECONDS, PAIR_TOKEN_TTL_SECONDS, PROTOCOL_VERSION, ROOT
from .semantic_risk import SemanticRiskEngine, provider_from_environment
from .realtime_pipeline import CALLER, CallerUtteranceBuffer, DualChannelPipeline, FinalAudioUtterance, Utterance
from .hybrid_v1 import HybridBrainV1, NomicSignal

PROCESS_LOOPBACK_SECONDS = 6
PREFERRED_PHONE_LINK_PROCESSES = ("phoneexperiencehost.exe", "yourphoneappproxy.exe", "crossdeviceservice.exe")


def discover_phone_link_candidates() -> list[dict[str, Any]]:
    """Return only dynamically discovered Phone Link/CrossDevice processes, ordered by render likelihood."""
    if platform.system() != "Windows":
        return []
    command = r'''$packages=Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object {$_.Name -like 'Microsoft.YourPhone*' -or $_.Name -like 'MicrosoftWindows.CrossDevice*'} | Select-Object Name,PackageFullName,InstallLocation
$processes=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Select-Object ProcessId,Name,ExecutablePath
[pscustomobject]@{packages=@($packages);processes=@($processes)} | ConvertTo-Json -Depth 4 -Compress'''
    try:
        completed = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        raw = json.loads(completed.stdout or "{}")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []
    packages = raw.get("packages", []) if isinstance(raw, dict) else []
    processes = raw.get("processes", []) if isinstance(raw, dict) else []
    if isinstance(packages, dict): packages = [packages]
    if isinstance(processes, dict): processes = [processes]
    candidates: list[dict[str, Any]] = []
    for process in processes:
        if not isinstance(process, dict):
            continue
        name = str(process.get("Name") or "")
        executable = str(process.get("ExecutablePath") or "")
        lowered_name, lowered_exe = name.lower(), executable.lower()
        package = next((item for item in packages if isinstance(item, dict) and str(item.get("InstallLocation") or "").lower() and lowered_exe.startswith(str(item.get("InstallLocation")).lower())), None)
        attributable = lowered_name in PREFERRED_PHONE_LINK_PROCESSES or package is not None or "microsoft.yourphone" in lowered_exe or "microsoftwindows.crossdevice" in lowered_exe
        if attributable and process.get("ProcessId"):
            candidates.append({"processName": name, "pid": int(process["ProcessId"]), "package": str((package or {}).get("Name") or "UNKNOWN"), "packageFullName": str((package or {}).get("PackageFullName") or ""), "executable": executable})
    priority = {name: index for index, name in enumerate(PREFERRED_PHONE_LINK_PROCESSES)}
    return sorted(candidates, key=lambda item: (priority.get(item["processName"].lower(), len(priority)), item["processName"].lower(), item["pid"]))


def invoke_native_process_loopback(helper: Path, candidate: dict[str, Any], wav: Path, seconds: int) -> dict[str, Any]:
    """Execute the native helper and normalize its sole JSON result into diagnostic evidence."""
    command = [str(helper), "--pid", str(candidate["pid"]), "--seconds", str(seconds), "--wav", str(wav)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=seconds + 15)
    except subprocess.TimeoutExpired:
        return {"error": "helper timed out"}
    except OSError as error:
        return {"error": f"helper launch failed: {type(error).__name__}"}
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    try:
        payload = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        return {"error": f"helper returned invalid JSON (exit {completed.returncode})"}
    if not isinstance(payload, dict):
        return {"error": "helper returned non-object JSON"}
    if completed.returncode != 0 and not payload.get("error"):
        payload["error"] = f"helper exited {completed.returncode}"
    return payload


class ScutService:
    """Thread-safe application state; all externally supplied values are validated by routes."""

    def __init__(self, port: int):
        self.port = port
        self.mode = "OFF"
        self.started = time.monotonic()
        self.transcripts: deque[str] = deque(maxlen=12)
        self.last_decision = Decision(Risk.SAFE, "Protection off", "SYSTEM")
        self.pair_tokens: dict[str, float] = {}
        self.devices: dict[str, dict[str, Any]] = read_json("devices.json", {})
        self.sessions: dict[str, queue.Queue[dict[str, Any]]] = {}
        self.events: deque[dict[str, Any]] = deque(maxlen=80)
        self.control_plane = ControlPlaneClient()
        self.incident_control = IncidentCoordinator()
        self._control_stop = threading.Event()
        self._control_thread: threading.Thread | None = None
        self.metrics: dict[str, float | None] = {"sttMs": None, "localDecisionMs": None, "alertDeliveryMs": None}
        self.anymodel_requests = 0
        self.anymodel_last_error: str | None = None
        # Semantic analysis is isolated from capture/ASR and starts with an
        # environment-configured provider when one is explicitly available.
        self.semantic_engine = SemanticRiskEngine(None, self._publish_risk_event)
        self.hybrid_brain = HybridBrainV1()
        self._nomic_deployment = None
        self._nomic_turns: deque[tuple[str, str]] = deque(maxlen=32)
        self.audio_status: dict[str, str] = {"state": "IDLE", "strategy": "NOT TESTED", "source": "-"}
        self._probe_at = 0.0
        self._machine_probe: dict[str, str] | None = None
        self._tailscale_probe = "NOT INSTALLED"
        self._guarded_stop = threading.Event()
        self._guarded_thread: threading.Thread | None = None
        self._user_mic_thread: threading.Thread | None = None
        self._asr_thread: threading.Thread | None = None
        self._realtime_pipeline = None
        self._dual_pass_pipeline = None
        self._contextual_caller_asr = None
        self._caller_utterance_buffer: CallerUtteranceBuffer | None = None
        self._caller_final_audio: queue.Queue[FinalAudioUtterance] = queue.Queue()
        self._caller_final_transcribe = None
        self._caller_accumulated_pcm = bytearray()
        self._caller_clock_ms = 0

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        connected = []
        for device_id, device in self.devices.items():
            age = now - float(device.get("lastHeartbeat", 0))
            if age <= HEARTBEAT_TTL_SECONDS:
                connected.append({"device": device.get("device", device_id), "status": "CONNECTED", "permissions": device.get("permissions", {})})
        machine = machine_config()
        if now - self._probe_at > 5 or self._machine_probe is None:
            self._machine_probe = detect_machine()
            self._tailscale_probe = detect_tailscale()
            self._probe_at = time.monotonic()
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "mode": self.mode,
            "uptimeSeconds": round(now - self.started, 1),
            "machine": self._machine_probe,
            "whisper": machine.get("whisper", {"device": "CPU", "selfTest": "NOT RUN"}),
            "audio": self.audio_status,
            "android": {"status": "CONNECTED" if connected else "OFFLINE", "devices": connected},
            "controlPlane": {**self.control_plane.status(), "decisionEpoch": self.incident_control.decision_epoch,
                             "liveSession": self.incident_control.session() is not None},
            "tailscale": self._tailscale_probe,
            "anyModel": {**anymodel_status(), "requests": self.anymodel_requests, "lastError": self.anymodel_last_error},
            "risk": {"level": self.last_decision.risk.value, "reason": self.last_decision.reason, "source": self.last_decision.source},
            "transcript": list(self.transcripts)[-1] if self.transcripts else "-",
            "metrics": self.metrics,
            "events": list(self.events)[-20:],
        }

    def set_mode(self, mode: str) -> dict[str, Any]:
        if self.mode == "TEST" and mode != "TEST":
            self.end_live_call()
        if mode != "TEST":
            self._guarded_stop.set()
        self.mode = mode
        self.last_decision = Decision(Risk.SAFE, "Protection off" if mode == "OFF" else "Waiting for stable caller speech", "SYSTEM")
        # A new call/mode gets isolated risk state. Network semantic extraction
        # is privacy-gated to PROTECT; local protection still runs in TEST.
        self.semantic_engine = SemanticRiskEngine(provider_from_environment() if mode == "PROTECT" else None, self._publish_risk_event)
        self.hybrid_brain = HybridBrainV1()
        self._nomic_deployment = None
        self._nomic_turns.clear()
        self.publish({"type": "status", "status": self.status()})
        return self.status()

    def begin_live_call(self) -> dict[str, Any]:
        """Start a session only when the real guarded-ASR path emits audio."""
        current = self.incident_control.session()
        if current is not None:
            return current
        session = self.incident_control.start_session(str(uuid.uuid4()), time.monotonic())
        self._sync_session(session, "ACTIVE")
        self.event("CALL_SESSION_STARTED", session["id"][:8])
        return session

    def end_live_call(self) -> None:
        ended = self.incident_control.end_session(time.monotonic())
        if ended is None:
            return
        self._sync_session(ended, "ENDED")
        self.event("CALL_SESSION_ENDED", ended["id"][:8])

    def process_controller_commands(self) -> list[dict[str, Any]]:
        """Apply leased cloud commands once, in arrival order, on the EXE."""
        results: list[dict[str, Any]] = []
        for command in self.control_plane.claim_commands():
            command_id = str(command["id"])
            if command["command_type"] == "VETO":
                result = self.incident_control.veto(time.monotonic())
                self.event("CONTROLLER_VETO", command_id[:8])
                dismissed, incident_synced = self._sync_active_state()
                if dismissed is not None:
                    if incident_synced:
                        self.control_plane.send_incident_notification(dismissed["id"])
                    else:
                        self.control_plane.defer_incident_notification(dismissed["id"])
                self.control_plane.complete_command(command_id, "APPLIED", None)
            else:
                result = self.incident_control.force(time.monotonic())
                self.event("CONTROLLER_FORCE", command_id[:8])
                if result["outcome"] == "INCIDENT":
                    incident = result["incident"]
                    incident_synced = self._sync_incident(incident)
                    # An accepted FCM message is not an assertion that Android
                    # displayed it or that the recipient acknowledged it.
                    if not incident_synced:
                        # The outbox preserves insertion order: the incident
                        # retry is sent before this stable-ID FCM retry.
                        self.event("INCIDENT_SYNC_QUEUED", incident["id"][:8])
                        self.control_plane.defer_incident_notification(incident["id"])
                    else:
                        self.control_plane.send_incident_notification(incident["id"])
                elif result["outcome"] == "NEUTRAL_TEST":
                    sent = self.control_plane.send_neutral_notification(command_id)
                    self.event("NEUTRAL_TEST_FCM_ACCEPTED" if sent else "NEUTRAL_TEST_FCM_QUEUED", command_id[:8])
                self.control_plane.complete_command(command_id, "APPLIED", None)
            results.append(result)
        return results

    def start_control_plane_worker(self) -> None:
        if self._control_thread and self._control_thread.is_alive():
            return
        self._control_stop.clear()
        self._control_thread = threading.Thread(target=self._control_worker, name="scut-control-plane", daemon=True)
        self._control_thread.start()

    def stop_control_plane_worker(self) -> None:
        self._control_stop.set()
        if self._control_thread:
            self._control_thread.join(timeout=2)

    def _control_worker(self) -> None:
        while not self._control_stop.wait(0.75):
            try:
                self.control_plane.flush_outbox()
                self.process_controller_commands()
            except Exception as error:
                # Never surface a cloud exception as a fabricated controller
                # action; the adapter will retry a leased command safely.
                self.event("CONTROL_PLANE_WORKER_ERROR", type(error).__name__)

    def _sync_active_state(self) -> tuple[dict[str, Any] | None, bool]:
        session = self.incident_control.session()
        if session:
            self._sync_session(session, "ACTIVE")
            incidents = self.incident_control.incidents()
            if incidents:
                incident = incidents[-1]
                return incident, self._sync_incident(incident)
        return None, True

    def _sync_session(self, session: dict[str, Any], state: str) -> None:
        self.control_plane.sync({"kind": "session", "id": session["id"], "startedAt": self._wall_time(session["startedAt"]),
                                 "endedAt": self._wall_time(session["endedAt"]) if session.get("endedAt") else None,
                                 "decisionEpoch": session["decisionEpoch"], "state": state})

    def _sync_incident(self, incident: dict[str, Any]) -> bool:
        source = "FORCE" if incident["forceCount"] else "AUTO"
        synced = self.control_plane.sync({"kind": "incident", "id": incident["id"], "sessionId": incident["sessionId"], "state": incident["state"],
                                          "source": source, "createdAt": self._wall_time(incident["createdAt"]), "updatedAt": self._wall_time(incident["updatedAt"]),
                                          "decisionEpoch": incident["decisionEpoch"], "forceCount": incident["forceCount"]})
        for index, text in enumerate(incident["transcript"]):
            self.control_plane.sync({"kind": "evidence", "incidentId": incident["id"], "evidenceType": "TRANSCRIPT",
                                     "eventId": str(uuid.uuid5(uuid.UUID(incident["id"]), f"transcript:{index}:{text}")),
                                     "occurredAt": self._wall_time(incident["updatedAt"]), "payload": {"text": text}})
        return synced

    @staticmethod
    def _wall_time(monotonic_at: float) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - max(0.0, time.monotonic() - monotonic_at)))

    def start_guarded_transcription(self) -> dict[str, Any]:
        if self.mode != "TEST":
            return {"state": "TEST_MODE_REQUIRED", "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED"}
        if self._guarded_thread and self._guarded_thread.is_alive():
            return {"state": "ALREADY_CAPTURING", "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED"}
        self._guarded_stop.clear()
        self.audio_status = {"state": "STARTING", "strategy": "SYSTEM_MIX_GUARDED", "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED"}
        # Capture producers never own Whisper.  This is the single bounded ASR
        # consumer shared by CALLER (priority) and USER channels.
        from .dual_pass_asr import ASRText, DualPassCallerASR
        from .guarded_audio import transcribe_fast_details, transcribe_pcm_details
        from .config import caller_asr_config
        asr = caller_asr_config()
        def fast(pcm: bytes) -> ASRText:
            value = transcribe_fast_details(pcm, asr["model"], device=asr["device"], compute_type=asr["computeType"])
            return ASRText(value["text"], value["language"], float(value["languageProbability"]))
        def accurate(pcm: bytes) -> ASRText:
            value = transcribe_pcm_details(pcm, vad_filter=False, model_name=asr["model"], device=asr["device"], compute_type=asr["computeType"])
            return ASRText(value["text"], value["language"], float(value["languageProbability"]))
        def final_details(pcm: bytes) -> dict[str, Any]:
            return transcribe_pcm_details(pcm, vad_filter=False, model_name=asr["model"], device=asr["device"], compute_type=asr["computeType"])
        self._dual_pass_pipeline = DualPassCallerASR(fast, accurate)
        # Caller PCM remains in memory through a VAD-defined endpoint.  The
        # final PCM is decoded once; no rolling Whisper text reaches UI/Nomic.
        self._contextual_caller_asr = None
        self._caller_utterance_buffer = CallerUtteranceBuffer()
        self._caller_final_audio = queue.Queue()
        self._caller_final_transcribe = final_details
        self._caller_accumulated_pcm = bytearray(); self._caller_clock_ms = 0
        self._guarded_thread = threading.Thread(target=self._guarded_worker, name="scut-guarded-whisper", daemon=True)
        self._guarded_thread.start()
        self._user_mic_thread = threading.Thread(target=self._user_mic_worker, name="scut-user-mic", daemon=True)
        self._user_mic_thread.start()
        self._asr_thread = threading.Thread(target=self._asr_worker, name="scut-priority-asr", daemon=True)
        self._asr_thread.start()
        return {"state": "STARTING", "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED"}

    def _guarded_worker(self) -> None:
        from .guarded_audio import capture_chunk
        if self._dual_pass_pipeline is None or self._caller_utterance_buffer is None:
            # Direct unit invocation keeps the old worker diagnostic harmless.
            self.audio_status = {"state": "SYSTEM_MIX_GUARDED_NOT_STARTED", "strategy": "SYSTEM_MIX_GUARDED", "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED"}
            return
        while self.mode == "TEST" and not self._guarded_stop.is_set():
            try:
                self.audio_status = {"state": "CAPTURING", "strategy": "SYSTEM_MIX_GUARDED", "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED"}
                pcm = capture_chunk(seconds=2)
                # The helper emits 48 kHz stereo PCM.  Frame it locally so
                # natural 750 ms pauses can close an utterance within a 2 s
                # capture block without allowing a Whisper partial.
                frame_bytes = 250 * 48_000 // 1000 * 4
                for offset in range(0, len(pcm), frame_bytes):
                    frame = pcm[offset:offset + frame_bytes]
                    start = self._caller_clock_ms
                    self._caller_clock_ms += round(len(frame) / (48_000 * 4) * 1000)
                    finalized = self._caller_utterance_buffer.ingest(frame, start, self._caller_clock_ms, voiced=DualChannelPipeline.has_speech(frame))
                    for utterance in finalized:
                        self._caller_final_audio.put_nowait(utterance)
            except RuntimeError as error:
                for utterance in self._caller_utterance_buffer.finish(self._caller_clock_ms):
                    self._caller_final_audio.put_nowait(utterance)
                self.audio_status = {"state": str(error), "strategy": "SYSTEM_MIX_GUARDED", "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED"}
                self._dual_pass_pipeline.set_safe_gap(True)
                self.publish({"type": "status", "status": self.status()})
                break

    def _asr_worker(self) -> None:
        """The only Whisper consumer; drains CALLER before USER without blocking capture."""
        while self.mode == "TEST" and not self._guarded_stop.is_set():
            try:
                utterance = self._caller_final_audio.get_nowait()
            except queue.Empty:
                utterance = None
            if utterance is not None and self._caller_final_transcribe is not None:
                from .whisper_quality import decode_with_optional_retry
                started = time.perf_counter()
                selection = decode_with_optional_retry(
                    utterance.pcm, utterance.retry_pcm,
                    max(0.0, (utterance.end_ms - utterance.start_ms) / 1000), self._caller_final_transcribe,
                )
                result = selection["selected_details"]
                self.metrics["sttMs"] = round((time.perf_counter() - started) * 1000, 1)
                text = str(result.get("text", "")).strip()
                if text:
                    self._record_live_final(text, CALLER)
                    self.transcript(text, explicit=False, speaker=CALLER)
                    self.audio_status = {"state": "FINAL_TRANSCRIPT", "strategy": "SYSTEM_MIX_GUARDED", "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED", "speaker": CALLER,
                                         "language": result.get("language"), "finalizationReason": utterance.reason,
                                         "retryOccurred": selection["retry_occurred"], "selectionReason": selection["selection_reason"]}
                    self.event("FINAL_TRANSCRIPT", f"{CALLER}: {text[:150]}")
                    self.publish({"type": "FINAL_TRANSCRIPT", "speaker": CALLER, "text": text, "audioStartMs": utterance.start_ms, "audioEndMs": utterance.end_ms})
                self.publish({"type": "status", "status": self.status()})
                continue
            pipeline = self._dual_pass_pipeline
            turn = pipeline.drain_once() if pipeline else None
            if not turn:
                time.sleep(.025)
                continue
            from .dual_pass_asr import FastPartial
            if isinstance(turn, FastPartial):
                self.audio_status = {"state": "FAST_PARTIAL", "strategy": "SYSTEM_MIX_GUARDED", "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED", "speaker": turn.speaker, "fastPartial": turn.text, "revisionId": turn.revision_id}
                self.event("FAST_CALLER_PARTIAL", f"{turn.speaker}: {turn.text[:150]}")
            else:
                self._record_live_final(turn.text, turn.speaker)
                self.transcript(turn.text, explicit=False, speaker=turn.speaker)
                self.audio_status = {"state": "STABLE_TRANSCRIPT", "strategy": "SYSTEM_MIX_GUARDED", "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED", "speaker": turn.speaker}
                self.event("STABLE_CALLER_TRANSCRIPT", f"{turn.speaker}: {turn.text[:150]}")
            self.publish({"type": "status", "status": self.status()})

    def _user_mic_worker(self) -> None:
        """Lower-priority USER source. It only queues audio; caller ASR consumes first."""
        from .guarded_audio import capture_user_chunk
        from .realtime_pipeline import USER, DualChannelPipeline
        clock_ms = 0
        while self.mode == "TEST" and not self._guarded_stop.is_set():
            try:
                if self._dual_pass_pipeline:
                    pcm = capture_user_chunk(seconds=2)
                    if DualChannelPipeline.has_speech(pcm):
                        self._dual_pass_pipeline.submit_fast(USER, pcm, clock_ms, clock_ms + 2000)
                    clock_ms += 2000
            except RuntimeError:
                break
            except Exception as error:
                self.audio_status = {"state": "ERROR", "strategy": "SYSTEM_MIX_GUARDED", "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED", "error": type(error).__name__}
                break

    def _record_live_final(self, text: str, speaker: str) -> None:
        session = self.begin_live_call()
        ended_at = time.monotonic()
        sequence = self.incident_control.append_final(session["id"], text, ended_at)
        event_id = str(uuid.uuid5(uuid.UUID(session["id"]), f"final:{sequence}"))
        self.control_plane.sync({"kind": "transcript", "eventId": event_id, "sessionId": session["id"], "sequence": sequence, "text": text,
                                 "speaker": speaker, "endedAt": self._wall_time(ended_at)})

    def pairing_payload(self, host: str) -> dict[str, Any]:
        token = new_secret(24)
        self.pair_tokens[token] = time.monotonic() + PAIR_TOKEN_TTL_SECONDS
        # host is selected from request Host header, not a persisted Computer-A address.
        return {"protocolVersion": PROTOCOL_VERSION, "endpoint": f"ws://{host}:{self.port}/ws", "pairingToken": token, "expiresInSeconds": PAIR_TOKEN_TTL_SECONDS}

    def pair(self, token: str, device: str, app_version: str, permissions: dict[str, Any]) -> dict[str, Any] | None:
        expiry = self.pair_tokens.pop(token, 0)
        if not expiry or time.monotonic() > expiry:
            return None
        credential = new_secret(32)
        device_id = hashlib.sha256(credential.encode()).hexdigest()[:16]
        self.devices[device_id] = {"credential": credential, "device": device[:120], "appVersion": app_version[:30], "permissions": permissions, "lastHeartbeat": time.monotonic()}
        from .config import atomic_json
        atomic_json("devices.json", self.devices, restrict=True)
        self.event("PAIR", f"Android paired: {device[:80]}")
        return {"type": "paired", "deviceId": device_id, "credential": credential, "protocolVersion": PROTOCOL_VERSION}

    def authenticate(self, credential: str) -> tuple[str, dict[str, Any]] | None:
        for device_id, device in self.devices.items():
            if credential and credential == device.get("credential"):
                return device_id, device
        return None

    def heartbeat(self, device_id: str, payload: dict[str, Any]) -> None:
        device = self.devices.get(device_id)
        if not device:
            return
        device["lastHeartbeat"] = time.monotonic()
        device["permissions"] = payload.get("permissions", {}) if isinstance(payload.get("permissions"), dict) else {}
        from .config import atomic_json
        atomic_json("devices.json", self.devices, restrict=True)
        self.publish({"type": "status", "status": self.status()})

    def transcript(self, text: str, explicit: bool = True, speaker: str = CALLER) -> dict[str, Any]:
        if self.mode == "OFF" and not explicit:
            return {"accepted": False, "reason": "Protection is OFF"}
        if self.transcripts and text == self.transcripts[-1]:
            return {"accepted": False, "reason": "Duplicate stable transcript", "risk": self.last_decision.risk.value}
        self.transcripts.append(text)
        started = time.perf_counter()
        # HTTP defaults to caller text; live ASR provides its preserved source.
        event = self.semantic_engine.ingest(Utterance(str(uuid.uuid4()), speaker, text, 0, 0, True))
        self._nomic_turns.append((speaker, text))
        nomic = self._nomic_signal()
        hybrid = self.hybrid_brain.ingest(Utterance(str(uuid.uuid4()), speaker, text, 0, 0, True), nomic)
        hybrid_risk = Risk.CRITICAL if hybrid["risk_level"] in {"HIGH_RISK", "CRITICAL"} else (Risk.SUSPICIOUS if hybrid["risk_level"] in {"WATCH", "SUSPICIOUS"} else Risk.SAFE)
        # Preserve a pre-existing cross-turn confirmed caller action while the
        # deployment Nomic adapter is unavailable. This is a conservative
        # compatibility floor, not a fabricated Nomic score.
        legacy_risk = Risk(event.level)
        if legacy_risk == Risk.CRITICAL and hybrid_risk != Risk.CRITICAL:
            hybrid["decision_trace"].append("legacy_confirmed_semantic_action_compatibility_floor")
            hybrid["risk_level"] = "CRITICAL"; hybrid["risk_score"] = max(hybrid["risk_score"], 80)
            hybrid["alert_recommended"] = True; hybrid["primary_reason_code"] = "CONFIRMED_CALLER_ACTION"
            hybrid_risk = Risk.CRITICAL
        decision = Decision(hybrid_risk, hybrid["primary_reason_code"], "HYBRID_BRAIN_V1")
        self.metrics["localDecisionMs"] = round((time.perf_counter() - started) * 1000, 1)
        self.metrics["semantic"] = dict(self.semantic_engine.latency)
        self.last_decision = decision
        result = {"accepted": True, "risk": decision.risk.value, "reason": decision.reason, "source": decision.source, "riskEvent": event.to_dict(), "hybrid": hybrid}
        self.event("TRANSCRIPT", text[:160])
        if self.mode == "PROTECT" and decision.risk == Risk.CRITICAL:
            if not self._queue_automatic_alert(decision, text):
                # Compatibility path for an explicit diagnostic or a legacy
                # producer with no real live-call session. It remains local.
                result["alert"] = self.send_alert(decision, text)
        self.publish({"type": "risk_event", "riskEvent": event.to_dict()})
        self.publish({"type": "decision", "decision": result, "status": self.status()})
        return result

    def _queue_automatic_alert(self, decision: Decision, text: str) -> bool:
        session = self.incident_control.session()
        if session is None:
            return False
        pending = self.incident_control.queue_automatic(session["id"], self.incident_control.decision_epoch, time.monotonic())
        if pending["outcome"] != "PENDING_AUTO":
            # VETO is intentionally not a blanket silence: it only suppresses
            # the pre-veto evidence until a later final transcript arrives.
            return True
        incident = pending["incident"]
        self._sync_incident(incident)
        timer = threading.Timer(self.incident_control.auto_hold_seconds, self._confirm_automatic_alert,
                                args=(incident["id"], incident["decisionEpoch"], decision, text))
        timer.daemon = True
        timer.start()
        self.event("AUTO_ALERT_PENDING", incident["id"][:8])
        return True

    def _confirm_automatic_alert(self, incident_id: str, decision_epoch: int, decision: Decision, text: str) -> None:
        confirmed = self.incident_control.confirm_automatic(incident_id, decision_epoch, time.monotonic())
        if confirmed["outcome"] != "CONFIRMED":
            return
        incident = confirmed["incident"]
        if self._sync_incident(incident):
            self.control_plane.send_incident_notification(incident["id"])
        else:
            self.control_plane.defer_incident_notification(incident["id"])
        self.send_alert(decision, text)
        self.event("AUTO_ALERT_CONFIRMED", incident["id"][:8])

    def _nomic_signal(self) -> NomicSignal:
        """Load the frozen local deployment only when PROTECT needs a score."""
        if self.mode != "PROTECT":
            return NomicSignal(source="DISABLED_OUTSIDE_PROTECT")
        try:
            if self._nomic_deployment is None:
                from .nomic_deployment_v1 import NomicDeploymentV1
                self._nomic_deployment = NomicDeploymentV1()
            return self._nomic_deployment.score(list(self._nomic_turns))
        except Exception as error:
            self.event("NOMIC_DEPLOYMENT_UNAVAILABLE", type(error).__name__)
            return NomicSignal(source="UNAVAILABLE_" + type(error).__name__)

    def _publish_risk_event(self, event) -> None:
        """Provider worker callback; it contains facts/event metadata, never a secret."""
        self.anymodel_last_error = None if event.provider_status == "AVAILABLE" else event.provider_status
        self.publish({"type": "risk_event", "riskEvent": event.to_dict()})

    def send_alert(self, decision: Decision, text: str, synthetic: bool = False) -> dict[str, Any]:
        alert = {"type": "alert", "id": str(uuid.uuid4()), "risk": decision.risk.value, "message": safe_warning(decision, text), "source": "TEST" if synthetic else decision.source, "sentMonotonic": time.monotonic()}
        delivered = 0
        for session_id, outbound in list(self.sessions.items()):
            try:
                outbound.put_nowait(alert)
                delivered += 1
            except queue.Full:
                self.sessions.pop(session_id, None)
        self.event("ALERT", f"{alert['risk']} sent to {delivered} connected client(s)")
        return {"id": alert["id"], "deliveredClients": delivered}

    def register_session(self) -> tuple[str, queue.Queue[dict[str, Any]]]:
        session_id, outbound = new_secret(12), queue.Queue(maxsize=32)
        self.sessions[session_id] = outbound
        return session_id, outbound

    def unregister_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    def publish(self, event: dict[str, Any]) -> None:
        for session_id, outbound in list(self.sessions.items()):
            try:
                outbound.put_nowait(event)
            except queue.Full:
                self.sessions.pop(session_id, None)

    def event(self, event_type: str, detail: str) -> None:
        self.events.append({"at": time.strftime("%H:%M:%S"), "type": event_type, "detail": detail})

    def acknowledge(self, alert_id: str, rendered_at: float | None = None) -> None:
        if rendered_at:
            self.metrics["alertDeliveryMs"] = round(max(0, time.monotonic() - rendered_at) * 1000, 1)
        self.event("ALERT_ACK", f"Android acknowledged {alert_id[:8]}")

    def diagnostic(self, name: str, source: str = "EXPLICIT_TEST_BUTTON") -> dict[str, Any]:
        if name == "guarded-transcription":
            return self.start_guarded_transcription()
        if name == "capture":
            return self._test_call_capture(source)
        if name == "earbuds":
            return {"state": "NEEDS OUTPUT SELECTION", "detail": "Select a Bluetooth A2DP output on this machine, then run the Windows helper."}
        if name == "network":
            return {"state": "PASS" if any(d.get("lastHeartbeat", 0) > time.monotonic() - HEARTBEAT_TTL_SECONDS for d in self.devices.values()) else "NO AUTHENTICATED ANDROID", "detail": "Application-level heartbeat is required."}
        if name == "predemo":
            checks = self.status()
            return {"state": "READY" if checks["android"]["status"] == "CONNECTED" else "BLOCKED", "checks": checks}
        return {"state": "UNKNOWN"}

    def _test_call_capture(self, source: str) -> dict[str, Any]:
        """Explicit-only process-scoped Phone Link capture. Endpoint PCM is never a PASS input."""
        test_id = str(uuid.uuid4())
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
        helper = ROOT / "windows-audio" / "scut-process-loopback.exe"
        candidates = discover_phone_link_candidates()
        attempts: list[dict[str, Any]] = []
        selected: dict[str, Any] | None = None
        reason = "NO_PHONE_LINK_PROCESS_AUDIO"
        if not helper.is_file():
            reason = "NATIVE_PROCESS_LOOPBACK_HELPER_MISSING"
        else:
            for index, candidate in enumerate(candidates):
                wav = DIAGNOSTICS / f"test_call_{test_id}_{index}_{candidate['pid']}.wav"
                result = invoke_native_process_loopback(helper, candidate, wav, PROCESS_LOOPBACK_SECONDS)
                attempt = {**candidate, "wav": str(wav), "duration": result.get("duration", PROCESS_LOOPBACK_SECONDS),
                           "sampleRate": result.get("sampleRate"), "channels": result.get("channels"), "samples": result.get("samples"),
                           "rms": result.get("rms"), "peak": result.get("peak"), "signal": bool(result.get("signal")), "error": result.get("error")}
                valid_wav = wav.is_file() and wav.stat().st_size > 44
                if attempt["signal"] and valid_wav and not attempt["error"]:
                    attempt["state"] = "PASS"
                    selected = attempt
                    attempts.append(attempt)
                    for remaining in candidates[index + 1:]:
                        attempts.append({**remaining, "wav": None, "duration": None, "sampleRate": None, "channels": None, "samples": None, "rms": None, "peak": None, "signal": False, "error": None, "state": "NOT TESTED"})
                    shutil.copy2(wav, DIAGNOSTICS / "test_call.wav")
                    reason = "PHONE_LINK_PROCESS_PCM_CAPTURED"
                    break
                attempt["state"] = "ERROR" if attempt["error"] else "SILENT"
                attempts.append(attempt)
        state = "PASS" if selected else "FAIL"
        if not candidates and reason == "NO_PHONE_LINK_PROCESS_AUDIO":
            reason = "NO_PHONE_LINK_CANDIDATES"
        payload = {"testId": test_id, "source": source, "timestamp": timestamp, "requestedSeconds": PROCESS_LOOPBACK_SECONDS,
                   "phoneLinkCandidateProcesses": candidates, "nativeProcessLoopbackAttempts": attempts, "selectedCandidate": selected,
                   "endpointLoopback": {"state": "NOT_USED_FOR_PASS", "detail": "Generic endpoint PCM cannot establish Phone Link capture."},
                   "finalState": state, "finalReason": reason}
        report = DIAGNOSTICS / "PHONE_LINK_AUDIO_DIAGNOSTIC.json"
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (DIAGNOSTICS / "PHONE_LINK_AUDIO_BLOCKER.md").write_text("# Phone Link audio diagnostic\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
        selected_name = selected["processName"] if selected else "No Phone Link process PCM"
        self.audio_status = {"state": state, "strategy": "NATIVE_PROCESS_LOOPBACK", "source": selected_name, "testId": test_id,
                             "candidates": attempts, "selected": selected}
        self.event("CAPTURE", f"test_id={test_id} source={source} {state}: {reason}")
        return {"testId": test_id, "source": source, "state": state, "reason": reason, "recording": str(DIAGNOSTICS / "test_call.wav") if selected else None,
                "selected": selected, "attempts": attempts, "report": str(report), "detail": reason}


def safe_warning(decision: Decision, text: str) -> str:
    if decision.risk == Risk.CRITICAL:
        lowered = text.lower()
        if "code" in lowered or "код" in lowered or "sms" in lowered:
            return "POSSIBLE SCAM — DO NOT SHARE THE SMS CODE"
        return "POSSIBLE SCAM — DO NOT SHARE FINANCIAL OR SECURITY DETAILS"
    return "SCUT warning"


def detect_machine() -> dict[str, str]:
    bluetooth = "UNKNOWN"
    if platform.system() == "Windows":
        try:
            result = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-PnpDevice -Class Bluetooth -Status OK -ErrorAction SilentlyContinue | Measure-Object).Count"], capture_output=True, text=True, timeout=5)
            bluetooth = "READY" if result.stdout.strip() not in {"", "0"} else "NOT DETECTED"
        except (OSError, subprocess.SubprocessError):
            bluetooth = "UNKNOWN"
    return {"windows": platform.platform(), "architecture": platform.machine() or "unknown", "bluetooth": bluetooth, "phoneLink": "DETECTED" if phone_link_present() else "NOT DETECTED"}


def phone_link_present() -> bool:
    if platform.system() != "Windows":
        return False
    command = "Get-AppxPackage Microsoft.YourPhone -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Name"
    try:
        return bool(subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=5).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def detect_tailscale() -> str:
    try:
        proc = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=5)
        if proc.returncode != 0:
            return "NEEDS LOGIN" if "Logged out" in proc.stderr else "NOT INSTALLED"
        return "READY" if json.loads(proc.stdout).get("BackendState") == "Running" else "NEEDS LOGIN"
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return "NOT INSTALLED"


def anymodel_status() -> dict[str, str | int]:
    # API credentials are environment-only. Never serialize or expose them.
    import os
    provider = os.getenv("SCUT_AI_PROVIDER", "anymodel").lower()
    model = os.getenv("SCUT_AI_MODEL", "kmc/k3" if provider == "anymodel" else "-")
    configured = bool(os.getenv("SCUT_AI_API_KEY")) and bool(os.getenv("SCUT_AI_BASE_URL", "https://anymodel.org/v1" if provider == "anymodel" else ""))
    return {"state": "READY" if configured else "NOT CONFIGURED", "provider": provider, "model": model, "requests": 0}
