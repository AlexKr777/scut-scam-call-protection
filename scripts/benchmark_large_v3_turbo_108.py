"""Locked 108-case, whole-utterance CUDA benchmark for large-v3-turbo.

This is diagnostics-only: it reads the existing fixtures and preserves the
existing semantic evaluator.  It does not import or alter FINALIZER V3 or the
streaming/capture paths.
"""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
import wave

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.acoustic_validation import PHRASES, polarity_inversion, semantic_fields, write_report
from backend.cuda_runtime import configure_cuda_dll_path

FIXTURES = ROOT / "diagnostics" / "tests" / "scam_acoustic_fixtures"
REPORTS = ROOT / "diagnostics"
STATUS = REPORTS / "TURBO_108_LATEST.status"
VARIANTS = ("clean", "mono16k", "telephone", "telephone_noise", "low_level", "compressed")


def status(value: str) -> None:
    STATUS.write_text(value + "\n", encoding="utf-8")


def gpu_snapshot() -> dict | None:
    fields = "memory.used,memory.total,utilization.gpu,temperature.gpu,pstate,clocks_throttle_reasons.active"
    try:
        row = subprocess.run(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=4, check=True).stdout.splitlines()[0]
        values = [x.strip() for x in row.split(",")]
        return {"memoryUsedMiB": int(values[0]), "memoryTotalMiB": int(values[1]),
                "utilizationPct": int(values[2]), "temperatureC": int(values[3]),
                "pstate": values[4], "throttleReasonsActive": values[5]}
    except Exception:
        return None


class Telemetry:
    def __init__(self):
        self.rows: list[dict] = []; self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)
    def sample(self) -> None:
        while not self.stop.is_set():
            row = gpu_snapshot()
            if row: self.rows.append(row | {"at": time.time()})
            self.stop.wait(.25)
    def __enter__(self): self.thread.start(); return self
    def __exit__(self, *_): self.stop.set(); self.thread.join(timeout=5)
    def summary(self) -> dict:
        if not self.rows: return {"available": False}
        return {"available": True, "samples": len(self.rows),
                "peakVramMiB": max(x["memoryUsedMiB"] for x in self.rows),
                "peakUtilizationPct": max(x["utilizationPct"] for x in self.rows),
                "peakTemperatureC": max(x["temperatureC"] for x in self.rows),
                "pstates": sorted(set(x["pstate"] for x in self.rows)),
                "thermalThrottlingObserved": any("Not Active" not in x["throttleReasonsActive"] for x in self.rows)}


def cases() -> list[dict]:
    # The authoritative 108-case manifest is the prior full-set run.  PHRASES
    # also contains later source entries for which this locked fixture set has
    # no WAV; derive IDs and source text from the existing 108-case manifest.
    manifest = ROOT / "diagnostics" / "small_cuda_float16_finalizer_v2_20260906-190536.json"
    rows = json.loads(manifest.read_text(encoding="utf-8"))["runs"][0]["cases"]
    result = []
    for row in rows:
        wav = FIXTURES / f"{row['id']}.wav"
        if not wav.is_file(): raise FileNotFoundError(f"Existing fixture missing: {wav}")
        result.append({key: row[key] for key in ("id", "language", "variant", "expectedSemanticClass", "sourceText")} | {"wav": wav})
    if len(result) != 108: raise RuntimeError(f"Expected 108 existing fixtures, found {len(result)}")
    return result


def duration(path: Path) -> float:
    with wave.open(str(path), "rb") as f: return f.getnframes() / f.getframerate()


def assess(text: str, returned_language: str, case: dict) -> dict:
    required = next(row[3] for row in PHRASES if row[:3] == (case["language"], case["expectedSemanticClass"], case["sourceText"]))
    fields = semantic_fields(text, case["language"], required)  # locked, existing evaluator
    stripped = text.strip()
    inversion = polarity_inversion(text, case["language"], case["expectedSemanticClass"])
    return {"semanticFields": fields, "pass": all(fields.values()), "negationPreserved": fields.get("negation"),
            "polarityInversion": inversion, "empty": not bool(stripped),
            "wrongLanguage": bool(returned_language and returned_language != case["language"]),
            "hallucinated": bool(stripped and not any(fields.values()))}


def percentile95(values: list[float]) -> float:
    ordered = sorted(values); return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * .95 + .999999))]


def main() -> int:
    status("RUNNING")
    try:
        configure_cuda_dll_path()
        import ctranslate2
        from faster_whisper import WhisperModel
        if ctranslate2.get_cuda_device_count() < 1: raise RuntimeError("CUDA unavailable; CPU fallback is prohibited")
        benchmark_cases = cases()
        before = gpu_snapshot(); loaded = time.perf_counter()
        with Telemetry() as telemetry:
            model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16", download_root=str(ROOT / ".local" / "models" / "huggingface"))
            load_seconds = time.perf_counter() - loaded
            output = []
            for index, case in enumerate(benchmark_cases):
                started = time.perf_counter()
                segments, info = model.transcribe(str(case["wav"]), language=case["language"], beam_size=1, temperature=0, condition_on_previous_text=False, vad_filter=False)
                transcript = " ".join(x.text.strip() for x in segments).strip()
                elapsed = time.perf_counter() - started; seconds = duration(case["wav"])
                output.append({k: v for k, v in case.items() if k != "wav"} | assess(transcript, str(info.language), case) | {"transcript": transcript, "returnedLanguage": str(info.language), "languageProbability": round(float(info.language_probability), 4), "inferenceSeconds": round(elapsed, 3), "audioSeconds": round(seconds, 3), "rtf": round(elapsed / seconds, 4), "cold": index == 0})
        after = gpu_snapshot(); warm = [x["inferenceSeconds"] for x in output[1:]]
        grouped = {name: [x for x in output if x["expectedSemanticClass"] == name] for name in ("dangerous", "protective", "context")}
        summary = {"pass": sum(x["pass"] for x in output), "total": len(output)} | {f"{name}Pass": sum(x["pass"] for x in group) for name, group in grouped.items()} | {f"{name}Total": len(group) for name, group in grouped.items()} | {"negationPreserved": sum(x["negationPreserved"] is True for x in output), "negationTotal": sum(x["negationPreserved"] is not None for x in output), "polarityInversions": [x["id"] for x in output if x["polarityInversion"]], "emptyResults": [x["id"] for x in output if x["empty"]], "hallucinatedResults": [x["id"] for x in output if x["hallucinated"]], "wrongLanguageResults": [x["id"] for x in output if x["wrongLanguage"]], "variantBreakdown": {v: {"pass": sum(x["pass"] for x in output if x["variant"] == v), "total": sum(x["variant"] == v for x in output)} for v in VARIANTS}}
        # Good enough requires an actual improvement over FINALIZER V2 and no meaning-flip.
        verdict = "TURBO_108_GOOD_ENOUGH" if summary["pass"] > 62 and not summary["polarityInversions"] else "TURBO_108_NOT_GOOD_ENOUGH"
        report = {"experiment": "TURBO_108_WHOLE_UTTERANCE_ACOUSTIC_VALIDATION", "design": {"fixtureCount": 108, "fixtureSource": "existing diagnostics/tests/scam_acoustic_fixtures", "semanticEvaluator": "backend.acoustic_validation.semantic_fields (unchanged)", "decode": {"model": "large-v3-turbo", "device": "cuda", "computeType": "float16", "explicitFixtureLanguage": True, "wholeUtterance": True, "beamSize": 1, "hotwords": None, "vadFilter": False, "conditionOnPreviousText": False}}, "cuda": {"deviceCount": int(ctranslate2.get_cuda_device_count()), "vramBeforeMiB": before["memoryUsedMiB"] if before else None, "vramAfterMiB": after["memoryUsedMiB"] if after else None}, "loadSeconds": round(load_seconds, 3), "latency": {"coldFirstInferenceSeconds": output[0]["inferenceSeconds"], "warmMedianSeconds": round(statistics.median(warm), 3), "warmP95Seconds": round(percentile95(warm), 3), "warmWorstSeconds": round(max(warm), 3), "overallRtf": round(sum(x["inferenceSeconds"] for x in output) / sum(x["audioSeconds"] for x in output), 4)}, "gpu": telemetry.summary(), "comparison": {"SMALL_108": "60/108 = 55.56%", "FINALIZER_V2": "62/108 = 57.41%"}, "summary": summary, "verdict": verdict, "cases": output}
        path = REPORTS / f"large_v3_turbo_cuda_float16_108_{time.strftime('%Y%m%d-%H%M%S')}.json"; write_report(report, path)
        status("FINISHED " + str(path)); print(json.dumps({"output": str(path), "verdict": verdict}, ensure_ascii=False)); return 0
    except Exception as exc:
        status("FAILED " + type(exc).__name__ + ": " + str(exc)); raise

if __name__ == "__main__": raise SystemExit(main())
