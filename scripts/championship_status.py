"""Pure runtime-status helpers shared by the Windows worker and tests."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from scripts.championship_common import atomic_json_write


def make_status(phase: str, current_fit: dict[str, Any] | None = None, **details: Any) -> dict[str, Any]:
    """Create a complete, JSON-safe status document with stable coordinates."""
    fit = current_fit or {}
    return {
        "pid": details.pop("pid", os.getpid()),
        "phase": phase,
        "candidate": fit.get("candidate"),
        "revision": fit.get("revision"),
        "depth": fit.get("depth"),
        "fold": fit.get("fold"),
        "seed": fit.get("seed"),
        "epoch": fit.get("epoch"),
        "fit_total": details.pop("fit_total", None),
        "fit_completed": details.pop("fit_completed", None),
        "stdout_log": details.pop("stdout_log", None),
        "stderr_log": details.pop("stderr_log", None),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        **details,
    }


def write_runtime_status(path: Path, status: dict[str, Any]) -> None:
    atomic_json_write(Path(path), status)


def pid_is_alive(pid: Any) -> bool:
    """Return process liveness without raising for a stale or malformed PID."""
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        os.kill(pid, 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


def bounded_status_lines(
    status: dict[str, Any], *, stdout_lines: Iterable[str] = (), stderr_lines: Iterable[str] = (), limit: int = 8
) -> list[str]:
    """Format a bounded status/log snapshot; callers own process/GPU probing."""
    if limit <= 0:
        raise ValueError("status log limit must be positive")
    coordinate = " ".join(f"{key}={status.get(key)}" for key in ("candidate", "revision", "depth", "fold", "seed", "epoch"))
    header = (
        f"phase={status.get('phase')} pid={status.get('pid')} alive={pid_is_alive(status.get('pid'))} "
        f"fits={status.get('fit_completed')}/{status.get('fit_total')} {coordinate}"
    )
    return [header, *list(stdout_lines)[-limit:], *list(stderr_lines)[-limit:]]
