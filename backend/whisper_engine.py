"""Whisper preparation/self-test run by bootstrap. CPU is always the safe baseline."""
from __future__ import annotations
import argparse
import json
import os
import time
import wave
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import machine_config, save_machine_config
from backend.constants import LOCAL, ROOT
from backend.cuda_runtime import configure_cuda_dll_path

MODEL_ID = "Systran/faster-whisper-small"


def model_dir() -> Path:
    return LOCAL / "models" / "faster-whisper-small"


def cached_hub_snapshot() -> Path | None:
    snapshots = LOCAL / "models" / "models--Systran--faster-whisper-small" / "snapshots"
    if snapshots.exists():
        for candidate in snapshots.iterdir():
            if (candidate / "model.bin").exists():
                return candidate
    return None


def update(device: str, state: str, error: str | None = None) -> None:
    config = machine_config(); config["whisper"] = {"model": MODEL_ID, "device": device, "selfTest": state, "error": error}; save_machine_config(config)


def prepare() -> int:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        update("CPU", "FAIL", "faster-whisper is not installed")
        print("Whisper dependency unavailable. Rerun FIRST_RUN after dependency stage.")
        return 1
    target = model_dir(); target.parent.mkdir(parents=True, exist_ok=True)
    try:
        source = str(target) if (target / "model.bin").exists() else str(cached_hub_snapshot() or MODEL_ID)
        model = WhisperModel(source, device="cpu", compute_type="int8", download_root=str(target.parent))
        # Model construction verifies model files. Inference follows in live diagnostics on a real utterance.
        del model
        update("CPU", "PASS")
        print(f"Whisper CPU model ready: {MODEL_ID}")
        return 0
    except Exception as error:
        update("CPU", "FAIL", str(error)[:240])
        print(f"Whisper preparation failed: {error}")
        return 1


def gpu_self_test() -> int:
    try:
        configure_cuda_dll_path()
        from faster_whisper import WhisperModel
        target = model_dir()
        if not target.exists():
            raise RuntimeError("CPU model is not prepared")
        model = WhisperModel(str(target), device="cuda", compute_type="float16")
        # Construction requires CTranslate2 CUDA libraries; it is the actual acceleration health check.
        del model; update("GPU", "PASS"); print("Whisper GPU self-test PASS"); return 0
    except Exception as error:
        update("CPU", "GPU FALLBACK", str(error)[:240]); print(f"Whisper GPU self-test failed; CPU retained: {error}"); return 0


if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--prepare",action="store_true");parser.add_argument("--gpu-self-test",action="store_true"); args=parser.parse_args()
    raise SystemExit(prepare() if args.prepare else gpu_self_test() if args.gpu_self_test else 2)
