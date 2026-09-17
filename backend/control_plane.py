"""Fail-closed Windows adapter for the Supabase command plane.

The adapter intentionally uses only the Edge Function surface.  The EXE never
has a Supabase service key, FCM credential, or direct database access.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import atomic_json, read_json


Transport = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class ControlPlaneConfig:
    url: str | None
    exe_token: str | None

    @classmethod
    def from_environment(cls) -> "ControlPlaneConfig":
        local = read_json("control_plane.json", {})
        local = local if isinstance(local, dict) else {}
        url = str(os.environ.get("SCUT_SUPABASE_URL") or local.get("url") or "").strip().rstrip("/")
        token = str(os.environ.get("SCUT_EXE_CONTROL_TOKEN") or local.get("exeToken") or "").strip()
        valid_url = url if url.startswith("https://") and ".supabase." in url else None
        valid_token = token if len(token) >= 24 else None
        return cls(valid_url, valid_token)

    @property
    def configured(self) -> bool:
        return bool(self.url and self.exe_token)


class ControlPlaneClient:
    def __init__(self, config: ControlPlaneConfig | None = None, transport: Transport | None = None):
        self.config = config or ControlPlaneConfig.from_environment()
        self._transport = transport or self._post
        self._last_error: str | None = None

    def status(self) -> dict[str, str]:
        if not self.config.configured:
            return {"state": "UNAVAILABLE", "reason": "CONTROL_PLANE_NOT_CONFIGURED"}
        if self._last_error:
            return {"state": "DEGRADED", "reason": self._last_error}
        return {"state": "AVAILABLE", "reason": "CONFIGURED"}

    def claim_commands(self, limit: int = 16) -> list[dict[str, Any]]:
        response = self._invoke("exe-commands", {"limit": max(1, min(limit, 64))})
        commands = response.get("commands", []) if response else []
        if not isinstance(commands, list):
            self._last_error = "INVALID_COMMAND_RESPONSE"
            return []
        return [item for item in commands if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("command_type") in {"FORCE", "VETO"}]

    def release_controller(self) -> dict[str, Any] | None:
        """Release the current controller through the protected EXE boundary."""
        response = self._invoke("release-controller", {})
        if not response or response.get("state") != "NO_CONTROLLER":
            return None
        return {"state": "NO_CONTROLLER", "released": response.get("released") is True}

    def list_history(self, cursor: str | None = None, limit: int = 25) -> dict[str, Any]:
        payload: dict[str, Any] = {"limit": max(1, min(limit, 50))}
        if cursor:
            payload["cursor"] = cursor
        return self._invoke("history-list", payload) or {"conversations": [], "nextCursor": None, "offline": True}

    def conversation_detail(self, conversation_id: str) -> dict[str, Any] | None:
        return self._invoke("conversation-detail", {"conversationId": conversation_id})

    def list_alerts(self, cursor: str | None = None, limit: int = 25) -> dict[str, Any]:
        payload: dict[str, Any] = {"limit": max(1, min(limit, 50))}
        if cursor:
            payload["cursor"] = cursor
        return self._invoke("alerts-list", payload) or {"alerts": [], "nextCursor": None, "offline": True}

    def delete_conversation(self, conversation_id: str) -> bool:
        response = self._invoke("conversation-delete", {"conversationId": conversation_id})
        return bool(response and response.get("deleted") is True)

    def sync(self, payload: dict[str, Any]) -> bool:
        if self._invoke("exe-sync", payload) is not None:
            return True
        self._queue("exe-sync", payload)
        return False

    def complete_command(self, command_id: str, state: str, reason: str | None = None) -> bool:
        payload: dict[str, Any] = {"kind": "command-result", "id": command_id, "state": state}
        if reason:
            payload["reason"] = reason[:160]
        return self.sync(payload)

    def send_incident_notification(self, incident_id: str) -> bool:
        payload = {"incidentId": incident_id}
        if self._invoke("send-fcm", payload) is not None:
            return True
        self._queue("send-fcm", payload)
        return False

    def defer_incident_notification(self, incident_id: str) -> None:
        """Queue a push behind a previously queued incident upsert."""
        self._queue("send-fcm", {"incidentId": incident_id})

    def send_neutral_notification(self, command_id: str) -> bool:
        """Send a connectivity test without creating or referencing an incident."""
        payload = {"kind": "NEUTRAL_TEST", "commandId": command_id}
        if self._invoke("send-fcm", payload) is not None:
            return True
        self._queue("send-fcm", payload)
        return False

    def flush_outbox(self) -> int:
        """Retry persisted work without changing its incident/event identity."""
        if not self.config.configured:
            return 0
        raw = read_json("control_plane_outbox.json", [])
        if not isinstance(raw, list):
            raw = []
        pending: list[dict[str, Any]] = []
        delivered = 0
        for item in raw[:64]:
            if not isinstance(item, dict) or not isinstance(item.get("function"), str) or not isinstance(item.get("payload"), dict):
                continue
            if self._invoke(item["function"], item["payload"]) is None:
                pending.append(item)
            else:
                delivered += 1
        atomic_json("control_plane_outbox.json", pending, restrict=True)
        return delivered

    def _queue(self, function: str, payload: dict[str, Any]) -> None:
        # A missing configuration is intentional, not a transient delivery
        # failure. Do not create an unbounded queue on an unconfigured PC.
        if not self.config.configured:
            return
        raw = read_json("control_plane_outbox.json", [])
        pending = raw if isinstance(raw, list) else []
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if not any(isinstance(item, dict) and item.get("function") == function and json.dumps(item.get("payload"), sort_keys=True, separators=(",", ":")) == canonical for item in pending):
            pending.append({"function": function, "payload": payload})
        atomic_json("control_plane_outbox.json", pending[-64:], restrict=True)

    def _invoke(self, function: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.config.configured:
            return None
        assert self.config.url is not None and self.config.exe_token is not None
        try:
            result = self._transport(
                f"{self.config.url}/functions/v1/{function}",
                payload,
                {"content-type": "application/json", "x-scut-exe-token": self.config.exe_token},
            )
            if not isinstance(result, dict):
                raise ValueError("invalid control-plane response")
            self._last_error = None
            return result
        except (OSError, ValueError, URLError):
            self._last_error = "CONTROL_PLANE_REQUEST_FAILED"
            return None

    @staticmethod
    def _post(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        request = Request(url, data=json.dumps(payload, separators=(",", ":")).encode("utf-8"), headers=headers, method="POST")
        with urlopen(request, timeout=5) as response:  # nosec B310: URL is validated configuration
            parsed = json.loads(response.read().decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("invalid control-plane response")
        return parsed
