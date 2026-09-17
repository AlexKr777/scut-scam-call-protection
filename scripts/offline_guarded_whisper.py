"""Offline validation for a saved SYSTEM_MIX_GUARDED PCM WAV; no capture occurs."""
from __future__ import annotations
import json
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.guarded_audio import transcribe_pcm_details

wav_path = ROOT / "diagnostics" / "guarded_system_mix_call_2.wav"
if not wav_path.is_file():
    wav_path = ROOT / "diagnostics" / "guarded_system_mix_call.wav"
with wave.open(str(wav_path), "rb") as wav:
    metadata = {"wav": str(wav_path), "duration": wav.getnframes() / wav.getframerate(), "sampleRate": wav.getframerate(), "channels": wav.getnchannels(), "bitsPerSample": wav.getsampwidth() * 8}
    pcm = wav.readframes(wav.getnframes())
started = time.perf_counter()
result = {**metadata, **transcribe_pcm_details(pcm), "transcriptionSeconds": round(time.perf_counter() - started, 3),
          "settings": {"model": "Systran/faster-whisper-small", "device": "cpu", "computeType": "int8", "beamSize": 1, "vadFilter": True, "inputConversion": "48 kHz stereo PCM -> mono -> 16 kHz"},
          "source": "SYSTEM_MIX_GUARDED", "attribution": "NOT_PROCESS_ATTRIBUTED"}
(ROOT / "diagnostics" / "GUARDED_SYSTEM_MIX_OFFLINE_WHISPER.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
