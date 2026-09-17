"""Fetch only the CPU int8 models needed by the local dual-pass benchmark."""
from pathlib import Path
from faster_whisper import WhisperModel

root = Path(__file__).resolve().parent.parent
for name in ("tiny", "base"):
    WhisperModel(f"Systran/faster-whisper-{name}", device="cpu", compute_type="int8", download_root=str(root / ".local" / "models"))
    print(f"{name} ready", flush=True)
