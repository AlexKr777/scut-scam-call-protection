"""Whole-utterance ASR comparison on the locked FINALIZER V3 hard subset.

This is intentionally independent of every streaming/finalizer component.  It
does not create audio, alter production configuration, prompt decoding with
expected text, or use semantic results to influence decoding.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import threading
import time
import wave

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.acoustic_validation import PHRASES, semantic_fields, write_report
from backend.cuda_runtime import configure_cuda_dll_path

FIXTURES = ROOT / "diagnostics" / "tests" / "scam_acoustic_fixtures"
REPORTS = ROOT / "diagnostics"


def gpu_snapshot() -> dict | None:
    """A lightweight NVIDIA sample.  None means telemetry was unavailable."""
    fields = "memory.used,memory.total,utilization.gpu,temperature.gpu,pstate,clocks_throttle_reasons.active"
    try:
        row = subprocess.run(
            ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4, check=True,
        ).stdout.splitlines()[0]
        value = [x.strip() for x in row.split(",")]
        return {"memoryUsedMiB": int(value[0]), "memoryTotalMiB": int(value[1]),
                "utilizationPct": int(value[2]), "temperatureC": int(value[3]),
                "pstate": value[4], "throttleReasonsActive": value[5]}
    except Exception:
        return None


class Telemetry:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self.stop.is_set():
            row = gpu_snapshot()
            if row:
                row["at"] = time.time()
                self.rows.append(row)
            self.stop.wait(0.25)

    def __enter__(self):
        self.thread.start(); return self

    def __exit__(self, *_):
        self.stop.set(); self.thread.join(timeout=5)

    def summary(self) -> dict:
        if not self.rows:
            return {"available": False}
        return {"available": True, "samples": len(self.rows),
                "typicalVramMiB": round(statistics.median(x["memoryUsedMiB"] for x in self.rows)),
                "peakVramMiB": max(x["memoryUsedMiB"] for x in self.rows),
                "peakUtilizationPct": max(x["utilizationPct"] for x in self.rows),
                "peakTemperatureC": max(x["temperatureC"] for x in self.rows),
                "pstates": sorted(set(x["pstate"] for x in self.rows)),
                "thermalThrottlingObserved": any("Not Active" not in x["throttleReasonsActive"] for x in self.rows)}


def locked_cases() -> list[dict]:
    candidates = sorted(REPORTS.glob("*finalizer_v3_hard_subset*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for report_path in candidates:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            cases = report["runs"][0]["cases"]
            if len(cases) == 24:
                result = []
                for case in cases:
                    wav = FIXTURES / f"{case['id']}.wav"
                    if not wav.is_file(): raise FileNotFoundError(wav)
                    result.append({key: case[key] for key in ("id", "language", "variant", "expectedSemanticClass", "sourceText") } | {"wav": wav})
                return result
        except (KeyError, IndexError, json.JSONDecodeError, FileNotFoundError):
            continue
    raise RuntimeError("Cannot locate the existing 24-case finalizer_v3_hard_subset report and fixtures")


def duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def stats(values: list[float]) -> dict:
    if not values: return {"medianSeconds": None, "p95Seconds": None, "worstSeconds": None}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, max(0, int((len(ordered) - 1) * .95 + .999999)))]
    return {"medianSeconds": round(statistics.median(values), 3), "p95Seconds": round(p95, 3), "worstSeconds": round(max(values), 3)}


def model_location(name: str) -> str:
    # The already provisioned SMALL model must remain local; other names are
    # resolved by faster-whisper's installed runtime into its documented cache.
    local = ROOT / ".local" / "models" / f"faster-whisper-{name}"
    if (local / "model.bin").is_file(): return str(local)
    cached = ROOT / "bootstrap-cache" / "models" / f"faster-whisper-{name}"
    return str(cached) if (cached / "model.bin").is_file() else name


def classify_case(text: str, returned_language: str, case: dict) -> dict:
    required = next(row[3] for row in PHRASES if row[:3] == (case["language"], case["expectedSemanticClass"], case["sourceText"]))
    fields = semantic_fields(text, case["language"], required)
    lower = text.lower().strip()
    # The legacy semantic evaluator intentionally uses loose substring tokens
    # for recall.  It sees the Russian dative word "мне" as containing "не";
    # that is unsuitable for the stricter SAFE/DANGEROUS inversion audit.
    negation_patterns = {
        "ru": r"(?<!\w)(?:не|никому|никогда)(?!\w)",
        "en": r"(?<!\w)(?:not|never|anyone)(?!\w)",
        "ro": r"(?<!\w)(?:nu|nimănui)(?!\w)",
    }
    negative = bool(re.search(negation_patterns[case["language"]], text, flags=re.IGNORECASE))
    empty = not lower
    # An asserted negation against a dangerous fixture is a SAFE inversion;
    # missing negation in a nonempty protective fixture is a DANGEROUS one.
    polarity = None
    if case["expectedSemanticClass"] == "dangerous" and negative:
        polarity = "SAFE_INSTEAD_OF_DANGEROUS"
    elif case["expectedSemanticClass"] == "protective" and not negative and not empty:
        polarity = "DANGEROUS_INSTEAD_OF_SAFE"
    return {"semanticFields": fields, "pass": all(fields.values()),
            "negationPreserved": fields.get("negation") if "negation" in required else None,
            "polarityInversion": polarity, "empty": empty,
            "wrongLanguage": bool(returned_language and returned_language != case["language"]),
            # A nonempty transcript with no required semantic evidence is the
            # reproducible, evaluator-based hallucination definition used here.
            "hallucinated": bool(lower and not any(fields.values()))}


def resolve_turbo_identifier() -> str:
    from faster_whisper.utils import available_models
    supported = available_models()
    for name in ("large-v3-turbo", "turbo"):
        if name in supported: return name
    raise RuntimeError("Installed faster-whisper exposes neither large-v3-turbo nor turbo")


def run_configuration(label: str, identifier: str, compute_type: str, cases: list[dict]) -> dict:
    configure_cuda_dll_path()
    import ctranslate2
    from faster_whisper import WhisperModel
    before = gpu_snapshot()
    started = time.perf_counter()
    with Telemetry() as telemetry:
        model = WhisperModel(model_location(identifier), device="cuda", compute_type=compute_type,
                             download_root=str(ROOT / ".local" / "models" / "huggingface"))
        load_seconds = time.perf_counter() - started
        results = []
        for index, case in enumerate(cases):
            began = time.perf_counter()
            segments, info = model.transcribe(str(case["wav"]), language=case["language"], beam_size=1,
                                               temperature=0, condition_on_previous_text=False, vad_filter=False)
            transcript = " ".join(segment.text.strip() for segment in segments).strip()
            elapsed = time.perf_counter() - began
            quality = classify_case(transcript, str(info.language), case)
            results.append({k: v for k, v in case.items() if k != "wav"} | quality | {
                "transcript": transcript, "returnedLanguage": str(info.language),
                "languageProbability": round(float(info.language_probability), 4),
                "inferenceSeconds": round(elapsed, 3), "audioSeconds": round(duration_seconds(case["wav"]), 3),
                "rtf": round(elapsed / duration_seconds(case["wav"]), 4), "cold": index == 0,
            })
    after = gpu_snapshot()
    warm = [x["inferenceSeconds"] for x in results[1:]]
    dangerous = [x for x in results if x["expectedSemanticClass"] == "dangerous"]
    protective = [x for x in results if x["expectedSemanticClass"] == "protective"]
    context = [x for x in results if x["expectedSemanticClass"] == "context"]
    return {"status": "READY", "model": label, "identifier": identifier, "device": "cuda", "computeType": compute_type,
            "ctranslate2CudaDevices": int(ctranslate2.get_cuda_device_count()), "loadSeconds": round(load_seconds, 3),
            "readiness": {"actualCudaUse": before is not None and after is not None and (after["memoryUsedMiB"] > before["memoryUsedMiB"] or telemetry.rows),
                          "transcriptProduced": bool(results[0]["transcript"]), "coldFirstInferenceSeconds": results[0]["inferenceSeconds"],
                          "vramBeforeMiB": before["memoryUsedMiB"] if before else None, "vramAfterMiB": after["memoryUsedMiB"] if after else None},
            "latency": {"coldFirstInferenceSeconds": results[0]["inferenceSeconds"], "warm": stats(warm),
                        "overallRtf": round(sum(x["inferenceSeconds"] for x in results) / sum(x["audioSeconds"] for x in results), 4)},
            "telemetry": telemetry.summary(), "cases": results,
            "summary": {"pass": sum(x["pass"] for x in results), "total": len(results), "dangerousPass": sum(x["pass"] for x in dangerous),
                        "dangerousTotal": len(dangerous), "protectivePass": sum(x["pass"] for x in protective), "protectiveTotal": len(protective),
                        "contextPass": sum(x["pass"] for x in context), "contextTotal": len(context),
                        "negationPreserved": sum(x["negationPreserved"] is True for x in results), "negationTotal": sum(x["negationPreserved"] is not None for x in results),
                        "polarityInversions": [x["id"] for x in results if x["polarityInversion"]], "emptyResults": [x["id"] for x in results if x["empty"]],
                        "hallucinatedResults": [x["id"] for x in results if x["hallucinated"]], "wrongLanguageResults": [x["id"] for x in results if x["wrongLanguage"]]}}


def attempt(label: str, identifier: str, computes: list[str], cases: list[dict]) -> dict:
    failures = []
    for compute in computes:
        try:
            return run_configuration(label, identifier, compute, cases)
        except Exception as exc:
            failures.append({"computeType": compute, "error": f"{type(exc).__name__}: {exc}"})
            gc.collect()
    return {"status": "NOT_FEASIBLE", "model": label, "identifier": identifier, "attempts": failures}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reclassify-report", type=Path,
                        help="Write a new report with corrected whole-word polarity auditing; performs no inference.")
    args = parser.parse_args()
    if args.reclassify_report:
        report = json.loads(args.reclassify_report.read_text(encoding="utf-8"))
        for model in report["models"]:
            if model.get("status") != "READY":
                continue
            inversions = []
            for case in model["cases"]:
                corrected = classify_case(case["transcript"], case["returnedLanguage"], case)
                case["polarityInversion"] = corrected["polarityInversion"]
                if corrected["polarityInversion"]:
                    inversions.append(case["id"])
            model["summary"]["polarityInversions"] = inversions
        report["analysisCorrection"] = {"kind": "whole-word negation polarity audit", "sourceReport": str(args.reclassify_report),
                                        "reason": "The semantic evaluator's recall-oriented substring rule may find не inside мне."}
        output = REPORTS / f"ASR_STRONGER_MODEL_HARD_SUBSET_{time.strftime('%Y%m%d-%H%M%S')}_POLARITY_CORRECTED.json"
        write_report(report, output)
        print(json.dumps({"output": str(output), "finalStatus": report["finalStatus"], "inferencePerformed": False}, ensure_ascii=False))
        return
    configure_cuda_dll_path()
    import ctranslate2
    if ctranslate2.get_cuda_device_count() < 1: raise SystemExit("NO_MODEL_READY: CUDA is unavailable; no CPU fallback permitted")
    cases = locked_cases()
    turbo = resolve_turbo_identifier()
    runs = [attempt("SMALL", "small", ["float16"], cases),
            attempt("MEDIUM", "medium", ["float16", "int8_float16"], cases),
            attempt("TURBO", turbo, ["float16", "int8_float16"], cases)]
    ready = [x for x in runs if x["status"] == "READY"]
    best = max(ready, key=lambda x: (x["summary"]["pass"], x["summary"]["dangerousPass"], x["summary"]["protectivePass"])) if ready else None
    final_status = "NO_MODEL_READY" if not best else f"{best['model']}_IS_BEST" if best["model"] != "SMALL" else "SMALL_REMAINS_BEST"
    report = {"experiment": "ASR_STRONGER_MODEL_HARD_SUBSET", "design": {"architecture": "independent whole-utterance model benchmark", "fixtureCount": len(cases),
              "fixtureSource": "existing finalizer_v3_hard_subset report", "decode": {"explicitFixtureLanguage": True, "conditionOnPreviousText": False, "temperature": 0, "beamSize": 1, "vadFilter": False, "hotwords": None}},
              "models": runs, "finalStatus": final_status, "bestModel": best["model"] if best else None}
    output = REPORTS / f"ASR_STRONGER_MODEL_HARD_SUBSET_{time.strftime('%Y%m%d-%H%M%S')}.json"
    write_report(report, output)
    print(json.dumps({"output": str(output), "finalStatus": final_status}, ensure_ascii=False))


if __name__ == "__main__": main()
