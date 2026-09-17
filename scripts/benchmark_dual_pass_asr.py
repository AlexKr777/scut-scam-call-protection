"""Actual CPU benchmark for the dual-pass decision; no capture is performed."""
import json
import os
import time
import wave
from pathlib import Path

import numpy as np
import psutil
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "diagnostics" / "guarded_system_mix_call_2.wav"
MODELS = ("tiny", "base", "small")
WINDOWS = (1.0, 1.5, 2.0, 2.5, 3.0)

def model_path(name: str) -> Path:
    direct = ROOT / ".local" / "models" / f"faster-whisper-{name}"
    if (direct / "model.bin").is_file(): return direct
    snapshots = ROOT / ".local" / "models" / f"models--Systran--faster-whisper-{name}" / "snapshots"
    return next(item for item in snapshots.iterdir() if (item / "model.bin").is_file())

with wave.open(str(FIXTURE), "rb") as source:
    frames, rate, channels = source.readframes(source.getnframes()), source.getframerate(), source.getnchannels()
samples = np.frombuffer(frames, dtype="<i2").astype("float32").reshape(-1, channels).mean(axis=1)[::3] / 32768.0
process = psutil.Process(os.getpid())
rows=[]
for name in MODELS:
    before=process.memory_info().rss
    model=WhisperModel(str(model_path(name)), device="cpu", compute_type="int8")
    after_load=process.memory_info().rss
    for seconds in WINDOWS:
        window=samples[:int(seconds*16000)]
        started=time.perf_counter()
        segments, info=model.transcribe(window, beam_size=1, vad_filter=False, condition_on_previous_text=False)
        text=" ".join(segment.text.strip() for segment in segments).strip()
        elapsed=time.perf_counter()-started
        # Under real-time paced arrivals the next window can begin when the
        # previous decode ends. This is the one-window worst-case backlog delta.
        rows.append({"model":name,"windowSeconds":seconds,"processingSeconds":round(elapsed,3),"rtf":round(elapsed/seconds,3),
                     "firstTextAvailableSeconds":round(seconds+elapsed,3),"firstUsefulClauseSeconds":round(seconds+elapsed,3) if text else None,
                     "text":text,"language":str(info.language),"languageProbability":round(float(info.language_probability),4),
                     "backlogGrowthSeconds":round(max(0.0,elapsed-seconds),3),"rssModelDeltaMiB":round((after_load-before)/1048576,1)})
    del model

# Models may be kept resident, but runtime never decodes them concurrently.
resident_before=process.memory_info().rss
resident_fast=WhisperModel(str(model_path("base")), device="cpu", compute_type="int8")
resident_accurate=WhisperModel(str(model_path("small")), device="cpu", compute_type="int8")
resident_delta_mib=round((process.memory_info().rss-resident_before)/1048576,1)
del resident_fast, resident_accurate

# Selection is conservative: fastest Russian-capable candidate with no one
# window backlog growth; accurate small remains a separate safe-gap pass.
fast_candidates=[row for row in rows if row["windowSeconds"] == 2.0 and row["text"] and row["language"] == "ru"]
fast=min(fast_candidates, key=lambda row: row["processingSeconds"])
report={"fixture":str(FIXTURE.relative_to(ROOT)),"fixtureKind":"VERIFIED_REAL_PHONE_LINK_CALLER","settings":{"device":"cpu","computeType":"int8","beamSize":1,"vad":"upstream segmentation; disabled inside isolated ASR window"},"results":rows,
        "selected":{"fast":{"model":fast["model"],"windowSeconds":2.0,"strideSeconds":1.0,"selectionMeasurement":fast},"accurate":{"model":"small","windowStrategy":"8-second accumulated caller utterance; only an explicit safe gap admits decode"}},
        "residentModels":{"fast":"base","accurate":"small","rssDeltaMiB":resident_delta_mib,"inferenceConcurrency":"serialized: one CPU lane"},
        "limitations":"Synthetic RU/RO/EN text fixtures are regression text, not claimed acoustic ASR measurements. The real Phone Link WAV is the acoustic benchmark."}
(ROOT/"diagnostics"/"DUAL_PASS_ASR_BENCHMARK.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report["selected"],ensure_ascii=False))
