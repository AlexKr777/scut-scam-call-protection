import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def local_root() -> Path:
    """Return the writable SCUT state directory for this runtime.

    Production launches set ``SCUT_LOCAL_DIR`` to Electron's per-user data
    directory.  A checkout deliberately retains its existing ``.local``
    layout when the variable is absent.
    """
    configured = os.environ.get("SCUT_LOCAL_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else ROOT / ".local"


def runtime_paths() -> tuple[Path, Path, Path]:
    local = local_root()
    return local, local / "logs", local / "diagnostics"


LOCAL, LOGS, DIAGNOSTICS = runtime_paths()
DEFAULT_PORT = 8765
PROTOCOL_VERSION = 1
MAX_BODY_BYTES = 64 * 1024
MAX_TRANSCRIPT_CHARS = 4000
PAIR_TOKEN_TTL_SECONDS = 300
HEARTBEAT_TTL_SECONDS = 20
