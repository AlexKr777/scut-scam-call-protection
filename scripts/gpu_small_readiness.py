"""Run one real GPU-small fixture and record a compact readiness result."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["SCUT_WHISPER_DEVICE"] = "cuda"

from backend.guarded_audio import transcribe_pcm_details

fixture = ROOT / "diagnostics" / "guarded_system_mix_call_2.wav"
started = time.perf_counter()
result = transcribe_pcm_details(fixture.read_bytes(), vad_filter=False, model_name="small")
report = {
    "fixture": str(fixture.relative_to(ROOT)),
    "device": "cuda",
    "model": "faster-whisper-small",
    "elapsedSeconds": round(time.perf_counter() - started, 3),
    "text": result["text"],
    "pass": bool(result["text"].strip()),
}
output = ROOT / "diagnostics" / "GPU_SMALL_READINESS.json"
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
raise SystemExit(0 if report["pass"] else 1)
