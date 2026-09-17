"""Authoritative, in-process call-session and incident state.

This module intentionally has no transport dependency.  The Windows service is
the source of truth; Supabase is an authenticated command and delivery plane,
not a second decision engine.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class _Session:
    id: str
    started_at: float
    transcript: list[dict[str, Any]] = field(default_factory=list)
    incident_id: str | None = None
    vetoed_at: float | None = None


class IncidentCoordinator:
    """Enforces FORCE/VETO ordering without inventing audio evidence."""

    def __init__(self, auto_hold_seconds: float = 1.5, force_dedup_seconds: float = 5.0):
        self.auto_hold_seconds = auto_hold_seconds
        self.force_dedup_seconds = force_dedup_seconds
        self.decision_epoch = 0
        self._session: _Session | None = None
        self._incidents: dict[str, dict[str, Any]] = {}
        self._last_force_at: float | None = None

    def start_session(self, session_id: str, started_at: float) -> dict[str, Any]:
        self._session = _Session(id=session_id, started_at=started_at)
        self._last_force_at = None
        return self.session()

    def end_session(self, ended_at: float) -> dict[str, Any] | None:
        if self._session is None:
            return None
        result = self.session()
        result["endedAt"] = ended_at
        self._session = None
        self._last_force_at = None
        return result

    def session(self) -> dict[str, Any] | None:
        if self._session is None:
            return None
        return {
            "id": self._session.id,
            "startedAt": self._session.started_at,
            "decisionEpoch": self.decision_epoch,
            "transcript": [item["text"] for item in self._session.transcript],
        }

    def append_final(self, session_id: str, text: str, ended_at: float) -> int:
        if self._session is None or self._session.id != session_id:
            raise ValueError("active session does not match transcript")
        normalized = text.strip()
        if normalized:
            self._session.transcript.append({"text": normalized, "endedAt": ended_at})
        return max(0, len(self._session.transcript) - 1)

    def force(self, now: float) -> dict[str, Any]:
        if self._session is None:
            return {"outcome": "NEUTRAL_TEST"}
        incident = self._incident_for_active_session("PENDING_FORCE", now)
        if self._last_force_at is None or now - self._last_force_at > self.force_dedup_seconds:
            incident["forceCount"] += 1
        self._last_force_at = now
        incident["updatedAt"] = now
        return {"outcome": "INCIDENT", "incident": deepcopy(incident)}

    def veto(self, now: float) -> dict[str, Any]:
        self.decision_epoch += 1
        dismissed = None
        if self._session is not None:
            self._session.vetoed_at = now
            if self._session.incident_id is not None:
                incident = self._incidents[self._session.incident_id]
                incident["state"] = "USER_DISMISSED"
                incident["decisionEpoch"] = self.decision_epoch
                incident["updatedAt"] = now
                dismissed = deepcopy(incident)
        result = {"outcome": "VETOED", "decisionEpoch": self.decision_epoch}
        if dismissed is not None:
            result["incident"] = dismissed
        return result

    def queue_automatic(self, session_id: str, decision_epoch: int, now: float) -> dict[str, Any]:
        if self._session is None or self._session.id != session_id:
            return {"outcome": "NO_ACTIVE_SESSION"}
        if decision_epoch != self.decision_epoch:
            return {"outcome": "STALE_DECISION"}
        if self._session.vetoed_at is not None:
            latest = self._session.transcript[-1] if self._session.transcript else None
            if latest is None or latest["endedAt"] <= self._session.vetoed_at:
                return {"outcome": "VETO_REQUIRES_FRESH_EVIDENCE"}
        incident = self._incident_for_active_session("PENDING_AUTO", now)
        incident["state"] = "PENDING_AUTO"
        incident["decisionEpoch"] = self.decision_epoch
        incident["holdUntil"] = now + self.auto_hold_seconds
        incident["updatedAt"] = now
        return {"outcome": "PENDING_AUTO", "incident": deepcopy(incident)}

    def confirm_automatic(self, incident_id: str, decision_epoch: int, now: float) -> dict[str, Any]:
        incident = self._incidents.get(incident_id)
        if incident is None:
            return {"outcome": "UNKNOWN_INCIDENT"}
        if decision_epoch != self.decision_epoch:
            return {"outcome": "STALE_DECISION", "incident": deepcopy(incident)}
        if incident["state"] != "PENDING_AUTO" or now < incident["holdUntil"]:
            return {"outcome": "NOT_READY", "incident": deepcopy(incident)}
        incident["state"] = "CONFIRMED"
        incident["updatedAt"] = now
        return {"outcome": "CONFIRMED", "incident": deepcopy(incident)}

    def incidents(self) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._incidents.values()]

    def _incident_for_active_session(self, state: str, now: float) -> dict[str, Any]:
        assert self._session is not None
        if self._session.incident_id is None:
            incident_id = str(uuid4())
            self._session.incident_id = incident_id
            self._incidents[incident_id] = {
                "id": incident_id,
                "sessionId": self._session.id,
                "state": state,
                "decisionEpoch": self.decision_epoch,
                "createdAt": now,
                "updatedAt": now,
                "forceCount": 0,
                "transcript": [item["text"] for item in self._session.transcript],
            }
        incident = self._incidents[self._session.incident_id]
        incident["transcript"] = [item["text"] for item in self._session.transcript]
        return incident
