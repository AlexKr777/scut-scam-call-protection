"""TEST-mode-only SYSTEM_MIX_GUARDED capture; raw PCM never reaches disk."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from .constants import ROOT

STREAM_HELPER = ROOT / "windows-audio" / "scut-guarded-mix-pcm-stream.exe"
MIC_STREAM_HELPER = ROOT / "windows-audio" / "scut-user-mic-pcm-stream.exe"
_models = {}

def _model_path(model_name: str) -> str:
    from .constants import LOCAL
    direct = LOCAL / "models" / f"faster-whisper-{model_name}"
    if (direct / "model.bin").is_file(): return str(direct)
    aliases = {"large-v3-turbo": ("models--mobiuslabsgmbh--faster-whisper-large-v3-turbo", "models--Systran--faster-whisper-large-v3-turbo")}
    prefixes = aliases.get(model_name, (f"models--Systran--faster-whisper-{model_name}",))
    for prefix in prefixes:
        snapshots = LOCAL / "models" / "huggingface" / prefix / "snapshots"
        if snapshots.is_dir():
            found = next((item for item in snapshots.iterdir() if (item / "model.bin").is_file()), None)
            if found: return str(found)
        snapshots = LOCAL / "models" / prefix / "snapshots"
        if snapshots.is_dir():
            found = next((item for item in snapshots.iterdir() if (item / "model.bin").is_file()), None)
            if found: return str(found)
    raise RuntimeError(f"WHISPER_MODEL_NOT_PREPARED_{model_name.upper().replace('-', '_')}")

def capture_chunk(seconds: int = 8) -> bytes:
    result = subprocess.run([str(STREAM_HELPER), "--seconds", str(seconds)], capture_output=True, timeout=seconds + 8)
    if result.returncode == 4:
        raise RuntimeError("CALL_SENTINEL_NOT_ACTIVE")
    if result.returncode or not result.stdout:
        raise RuntimeError(f"GUARDED_CAPTURE_FAILED_{result.returncode}")
    return result.stdout

def capture_user_chunk(seconds: int = 4) -> bytes:
    result = subprocess.run([str(MIC_STREAM_HELPER), "--seconds", str(seconds)], capture_output=True, timeout=seconds + 8)
    if result.returncode or not result.stdout: raise RuntimeError(f"USER_MIC_CAPTURE_FAILED_{result.returncode}")
    return result.stdout

def transcribe_pcm_details(pcm: bytes, vad_filter: bool = True, model_name: str = "small", language: str | None = None, hotwords: str | None = None, beam_size: int = 1, device: str | None = None, compute_type: str | None = None) -> dict:
    """One lazily cached model per named pass; callers must serialize CPU inference."""
    import numpy as np
    from .cuda_runtime import configure_cuda_dll_path
    configure_cuda_dll_path()
    from faster_whisper import WhisperModel
    samples = np.frombuffer(pcm, dtype="<i2").astype("float32").reshape(-1, 2).mean(axis=1)[::3] / 32768.0
    if model_name not in {"tiny", "base", "small", "large-v3-turbo"}:
        raise ValueError("unsupported Whisper model")
    resolved_device = (device or os.environ.get("SCUT_WHISPER_DEVICE", "cpu")).lower()
    resolved_compute = compute_type or ("float16" if resolved_device == "cuda" else "int8")
    if resolved_device not in {"cpu", "cuda"}:
            raise RuntimeError("SCUT_WHISPER_DEVICE must be cpu or cuda")
    key = (model_name, resolved_device, resolved_compute)
    if key not in _models:
        _models[key] = WhisperModel(_model_path(model_name), device=resolved_device, compute_type=resolved_compute)
    segments, info = _models[key].transcribe(samples, beam_size=beam_size, vad_filter=vad_filter,
        condition_on_previous_text=False, language=language, hotwords=hotwords)
    rows = list(segments)
    scores = [float(getattr(row, "avg_logprob", 0.0)) for row in rows]
    no_speech = [float(getattr(row, "no_speech_prob", 0.0)) for row in rows]
    segment_rows = [{"start": float(row.start), "end": float(row.end), "avgLogProb": float(getattr(row, "avg_logprob", 0.0)),
                     "noSpeechProbability": float(getattr(row, "no_speech_prob", 0.0)), "compressionRatio": float(getattr(row, "compression_ratio", 0.0))}
                    for row in rows]
    return {"text": " ".join(segment.text.strip() for segment in rows).strip(), "language": str(info.language),
            "languageProbability": str(round(float(info.language_probability), 4)),
            "averageLogProb": str(round(sum(scores) / len(scores), 4)) if scores else "", "noSpeechProbability": str(round(max(no_speech), 4)) if no_speech else "",
            "compressionRatio": str(round(max((x["compressionRatio"] for x in segment_rows), default=0.0), 4)), "segments": segment_rows}

def transcribe_pcm(pcm: bytes) -> str:
    return transcribe_pcm_details(pcm, vad_filter=False, model_name="small")["text"]

def transcribe_fast_details(pcm: bytes, model_name: str = "base", language: str | None = None, hotwords: str | None = None, device: str | None = None, compute_type: str | None = None) -> dict[str, str]:
    """FAST caller decoder: faster-whisper-base CPU int8 by default."""
    return transcribe_pcm_details(pcm, vad_filter=False, model_name=model_name, language=language, hotwords=hotwords, device=device, compute_type=compute_type)
