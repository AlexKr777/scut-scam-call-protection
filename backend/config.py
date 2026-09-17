import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any

from .constants import LOCAL


def ensure_local() -> Path:
    LOCAL.mkdir(parents=True, exist_ok=True)
    return LOCAL


def _path(name: str) -> Path:
    return ensure_local() / name


def read_json(name: str, default: Any) -> Any:
    path = _path(name)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_json(name: str, value: Any, restrict: bool = False) -> None:
    path = _path(name)
    temp = path.with_suffix(path.suffix + ".partial")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
    username = os.environ.get("USERNAME", "").strip()
    if restrict and os.name == "nt" and username:
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:F"], capture_output=True, check=False)


def machine_config() -> dict[str, Any]:
    return read_json("machine.json", {"port": 8765, "whisper": {"profile": "turbo_cuda", "model": "large-v3-turbo", "device": "cuda", "computeType": "float16", "recovery": {"model": "small", "device": "cpu", "computeType": "int8"}, "selfTest": "NOT RUN"}})

def caller_asr_config() -> dict[str, str]:
    """Single caller-ASR profile; recovery is opt-in, never an implicit fallback."""
    profile = os.environ.get("SCUT_ASR_MODE", "turbo_cuda").lower()
    configured = machine_config().get("whisper", {})
    if profile == "recovery":
        recovery = configured.get("recovery", {})
        return {"profile": "recovery", "model": str(recovery.get("model", "small")), "device": str(recovery.get("device", "cpu")).lower(), "computeType": str(recovery.get("computeType", "int8"))}
    if profile != "turbo_cuda":
        raise RuntimeError("SCUT_ASR_MODE must be turbo_cuda or recovery")
    return {"profile": "turbo_cuda", "model": str(configured.get("model", "large-v3-turbo")), "device": str(configured.get("device", "cuda")).lower(), "computeType": str(configured.get("computeType", "float16"))}


def save_machine_config(data: dict[str, Any]) -> None:
    atomic_json("machine.json", data)


def new_secret(size: int = 32) -> str:
    return secrets.token_urlsafe(size)
