"""Immutable, end-to-end Audio Replay V1 utilities.

The replay bench deliberately feeds PCM through ``DualChannelPipeline`` and
the production ``guarded_audio.transcribe_pcm_details`` function.  Reference
text is retained exclusively for evaluation after inference has completed.
"""
from __future__ import annotations

import audioop
import csv
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .constants import LOCAL, ROOT

DATA = ROOT / "data" / "audio_replay_v1"
REPORTS = ROOT / "reports" / "audio_replay_v1"
RUNTIME = ROOT / "runtime" / "audio_replay_v1"
STABILIZER_V3_REPORTS = ROOT / "reports" / "audio_replay_v1_stabilizer_v3"
STABILIZER_V3_RUNTIME = ROOT / "runtime" / "audio_replay_v1_stabilizer_v3"
STREAMING_PIPELINE_VERSION = "STREAMING_TRANSCRIPT_STABILIZER_V3"
UTTERANCE_REPORTS = ROOT / "reports" / "audio_replay_v1_utterance_whisper"
UTTERANCE_RUNTIME = ROOT / "runtime" / "audio_replay_v1_utterance_whisper"
UTTERANCE_PIPELINE_VERSION = "WHOLE_UTTERANCE_WHISPER_V1"
WHISPER_QUALITY_V2_REPORTS = ROOT / "reports" / "whisper_quality_v2"
WHISPER_QUALITY_V2_RUNTIME = ROOT / "runtime" / "whisper_quality_v2"
WHISPER_QUALITY_V2_PIPELINE_VERSION = "WHOLE_UTTERANCE_WHISPER_QUALITY_V2"
MANIFEST = DATA / "source_manifest.json"
LOCK = DATA / "audio_replay_v1_manifest.lock.json"
STATUS = RUNTIME / "status.json"
STOP = RUNTIME / "stop.request"
THRESHOLD_SOURCE = ROOT / "reports" / "scut_brain_championship_v3_pc5070" / "experiment_nonlinear_head__bf16_precisionfix__seed_17.json"
CHECKPOINT = ROOT / "output" / "hybrid_v1" / "NOMIC_DEPLOYMENT_V1" / "model.pt"
EXPECTED_CHECKPOINT_SHA256 = "4D436D29DCB76AFDF86538E336E4B22DF413F840274EF56856A72FCB30F19E20"
PCM_RATE = 48_000
PCM_CHANNELS = 2
WINDOW_MS = 2_000
STRIDE_MS = 1_000
VAD_FRAME_MS = 250
VAD_ENDPOINT_SILENCE_MS = 750
MAX_UTTERANCE_MS = 12_000


def configure_d_drive_caches() -> dict[str, str]:
    """Keep model/cache/temp writes inside the configured local runtime."""
    base = Path(os.environ.get("SCUT_ML_CACHE_DIR", LOCAL / "ml-cache"))
    locations = {
        "HF_HOME": base / "hf-cache", "HF_HUB_CACHE": base / "hf-cache", "TRANSFORMERS_CACHE": base / "hf-cache",
        "XDG_CACHE_HOME": base / "audio-replay-cache", "TEMP": base / "audio-replay-cache", "TMP": base / "audio-replay-cache",
    }
    for location in set(locations.values()):
        location.mkdir(parents=True, exist_ok=True)
    for key, location in locations.items():
        os.environ[key] = str(location)
    return {key: str(value) for key, value in locations.items()}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as temporary:
            temporary_name = temporary.name
            json.dump(value, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        Path(temporary_name).replace(path)
    finally:
        if temporary_name and Path(temporary_name).exists():
            Path(temporary_name).unlink()


def normalise_wav(source: Path, target: Path) -> float:
    """Produce the exact 48 kHz stereo PCM16 format consumed by SCUT capture."""
    with wave.open(str(source), "rb") as handle:
        raw, rate, channels, width = handle.readframes(handle.getnframes()), handle.getframerate(), handle.getnchannels(), handle.getsampwidth()
    if width != 2 or channels not in {1, 2}:
        raise ValueError(f"unsupported WAV format: {source} ({channels}ch/{width * 8}bit)")
    if channels == 1:
        raw = audioop.tostereo(raw, 2, 1, 1)
    if rate != PCM_RATE:
        raw = audioop.ratecv(raw, 2, PCM_CHANNELS, rate, PCM_RATE, None)[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(PCM_CHANNELS)
        handle.setsampwidth(2)
        handle.setframerate(PCM_RATE)
        handle.writeframes(raw)
    return round(len(raw) / (PCM_RATE * PCM_CHANNELS * 2), 3)


def load_pcm(path: Path) -> tuple[bytes, float]:
    with wave.open(str(path), "rb") as handle:
        if (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) != (PCM_RATE, PCM_CHANNELS, 2):
            raise ValueError(f"replay audio is not normalised: {path}")
        raw = handle.readframes(handle.getnframes())
    return raw, len(raw) / (PCM_RATE * PCM_CHANNELS * 2)


def fixture_sources() -> list[dict[str, Any]]:
    """Known local SAPI fixtures, explicitly labelled synthetic—not intercepted calls."""
    from .acoustic_validation import PHRASES
    rows: list[dict[str, Any]] = []
    fixtures = ROOT / "diagnostics" / "tests" / "scam_acoustic_fixtures"
    label = {"dangerous": "dangerous", "protective": "protective", "context": "mixed_context"}
    for number, (language, kind, script, _) in enumerate(PHRASES, 1):
        source = fixtures / f"{number:02d}_{language}_{kind}__clean.wav"
        if not source.is_file():
            continue
        case_id = f"synthetic_{language}_{number:02d}_{kind}"
        rows.append({
            "source_id": case_id, "case_id": case_id, "title": f"Synthetic SCUT acoustic control {number:02d}",
            "publisher": "SCUT local diagnostic fixture", "resolved_url": None, "media_url": None,
            "language": language, "source_type": "SYNTHETIC", "expected_class": label[kind],
            "scam_family": "credential_or_payment" if kind == "dangerous" else "protective_advice" if kind == "protective" else "context_only",
            "download_status": "LOCAL_SYNTHETIC_READY", "usage_note": "Generated with a generic local SAPI voice for E2E engineering replay; it is not a real call.",
            "license_or_terms_note": "Local SCUT diagnostic fixture; no third-party recording is redistributed.",
            "strict_score_eligible": False, "reference_transcript_available": True, "reference_transcript": script,
            "reference_transcript_clip_aligned": True, "original_path": str(source), "original_sha256": sha256_file(source),
            "duration_sec": None, "capture_equivalence": "PRODUCTION_EQUIVALENT", "speaker_topology": "REMOTE_CALLER_ONLY",
            "tts_engine": "Windows SAPI", "voice_metadata": "generic local installed voice", "scenario_references": ["SCUT diagnostic synthetic scenario"],
        })
    return rows


def reference_only_sources() -> list[dict[str, Any]]:
    """Candidates are deliberately non-scoring until a lawful direct asset is reviewed."""
    candidates = [
        ("ftc_apple_tech_support", "Apple tech support scam", "Federal Trade Commission", "en"),
        ("ftc_irs_impersonator", "IRS impersonator scam", "Federal Trade Commission", "en"),
        ("ftc_interest_rate", "Interest rate reduction scam", "Federal Trade Commission", "en"),
        ("ftc_utility_impersonator", "Utility company impersonator scam", "Federal Trade Commission", "en"),
        ("ftc_family_emergency", "Family Emergency Imposter Scams", "Federal Trade Commission", "en"),
        ("ftc_tech_support", "Tech Support Imposter Scams", "Federal Trade Commission", "en"),
        ("ftc_how_scammers_pay", "How Scammers Tell You To Pay", "Federal Trade Commission", "en"),
        ("astv_real_call", "Реальный разговор с мошенником", "ASTV / police source", "ru"),
        ("ema_real_call", "Как мы звонили мошенникам", "EMA", "ru"),
        ("ema_safe_card", "Safe Card: разоблачение телефонного мошенника", "EMA", "ru"),
        ("tbank_fraud_roulette", "Фрод-рулетка", "T-Bank", "ru"),
        ("stirileprotv_fake_bank", "Cum să recunoști apelurile false de la bănci", "Știrile ProTV", "ro"),
        ("politia_md_warning", "O nouă metodă de escrocherie-fiți vigilenți!", "Poliția Republicii Moldova", "ro"),
    ]
    return [{
        "source_id": ident, "title": title, "publisher": publisher, "resolved_url": None, "media_url": None,
        "language": language, "source_type": "REFERENCE_ONLY", "expected_class": "mixed_context",
        "scam_family": "source_review_pending", "download_status": "REFERENCE_ONLY", "usage_note": "No direct media was automatically acquired; requires page-specific terms and media review.",
        "license_or_terms_note": "Not assessed as reusable audio.", "strict_score_eligible": False,
        "reference_transcript_available": False, "original_sha256": None, "duration_sec": None,
        "capture_equivalence": "UNKNOWN", "speaker_topology": "UNKNOWN",
    } for ident, title, publisher, language in candidates]


def optional_unverified_source() -> dict[str, Any]:
    return {
        "source_id": "github_cybersorceress_dataset", "title": "Scam-Call-Detection / Data/dataset.zip", "publisher": "CyberSorceress GitHub repository",
        "resolved_url": "https://github.com/CyberSorceress/Scam-Call-Detection", "media_url": "https://raw.githubusercontent.com/CyberSorceress/Scam-Call-Detection/main/Data/dataset.zip",
        "language": "unknown", "source_type": "OPTIONAL_UNVERIFIED_SOURCE", "expected_class": "mixed_context", "scam_family": "unknown",
        "download_status": "NOT_DOWNLOADED", "usage_note": "Repository has no declared license and the supplied citation does not establish recording provenance.",
        "license_or_terms_note": "No repository license; no dataset-specific license or provenance identified. Excluded from strict scoring and local replay.",
        "strict_score_eligible": False, "reference_transcript_available": False, "original_sha256": None, "duration_sec": None,
        "capture_equivalence": "UNKNOWN", "speaker_topology": "UNKNOWN", "github_blob_sha": "e5b27b6738bdc0bd2505639896f239820f9ed902", "dataset_zip_bytes": 23070589,
    }


def prepare_pack() -> dict[str, Any]:
    DATA.mkdir(parents=True, exist_ok=True)
    rows = fixture_sources() + reference_only_sources() + [optional_unverified_source()]
    seen_hashes: set[str] = set()
    for row in rows:
        source = row.get("original_path")
        if not source:
            continue
        target = DATA / "audio" / f"{row['case_id']}.wav"
        duration = normalise_wav(Path(source), target)
        content_hash = sha256_file(target)
        row.update({"audio_path": str(target), "audio_sha256": content_hash, "duration_sec": duration, "download_status": "READY"})
        # A generated script/audio may occur only once in headline metrics.
        duplicate = content_hash in seen_hashes
        seen_hashes.add(content_hash)
        independently_grounded = row["source_type"] == "SYNTHETIC" and bool(row.get("reference_transcript"))
        row["strict_score_eligible"] = bool(independently_grounded and not duplicate and row["expected_class"] in {"dangerous", "protective", "legitimate"})
        row["deduplication"] = "UNIQUE" if not duplicate else "DUPLICATE_EXCLUDED"
    atomic_json_write(MANIFEST, {"schema_version": 1, "created_at": now(), "cases": rows, "notes": {"github_dataset": "OPTIONAL_UNVERIFIED_SOURCE; not downloaded or used", "raw_media_policy": "Only locally generated diagnostics are present in this pack."}})
    lock = lock_manifest(rows)
    atomic_json_write(LOCK, lock)
    return {"manifest": str(MANIFEST), "lock": str(LOCK), "pack_sha256": lock["pack_sha256"], "prepared": sum(x.get("download_status") == "READY" for x in rows)}


def lock_manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    frozen: list[dict[str, Any]] = []
    for raw in sorted(rows, key=lambda value: value.get("case_id") or value.get("source_id") or ""):
        row = dict(raw)
        row.setdefault("strict_score_eligible", False)
        if row.get("audio_path") and Path(row["audio_path"]).is_file():
            row["audio_sha256"] = sha256_file(Path(row["audio_path"]))
        frozen.append(row)
    body = {"schema_version": 1, "locked_at": now(), "cases": frozen}
    canonical = json.dumps({"schema_version": body["schema_version"], "cases": frozen}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body["pack_sha256"] = hashlib.sha256(canonical).hexdigest().upper()
    return body


def verify_preflight() -> dict[str, Any]:
    cache_paths = configure_d_drive_caches()
    if not LOCK.is_file():
        raise RuntimeError("AUDIO_REPLAY_PACK_LOCK_MISSING: run prepare before any replay")
    if not CHECKPOINT.is_file() or sha256_file(CHECKPOINT) != EXPECTED_CHECKPOINT_SHA256:
        raise RuntimeError("NOMIC_CHECKPOINT_SHA_MISMATCH")
    threshold_doc = json.loads(THRESHOLD_SOURCE.read_text(encoding="utf-8"))
    threshold = threshold_doc.get("selected_threshold")
    if not isinstance(threshold, (float, int)):
        raise RuntimeError("NOMIC_AUTHORITATIVE_THRESHOLD_UNRECOVERABLE")
    import torch, transformers, faster_whisper  # noqa: F401
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "NOT_A_GIT_REPOSITORY"
    return {"git_revision": revision, "exact_command_line": subprocess.list2cmdline(sys.argv), "checkpoint_sha256": EXPECTED_CHECKPOINT_SHA256, "threshold": float(threshold), "threshold_source": str(THRESHOLD_SOURCE), "threshold_source_sha256": sha256_file(THRESHOLD_SOURCE), "python": platform.python_version(), "torch": torch.__version__, "transformers": transformers.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None, "whisper": "Systran/faster-whisper-small / faster-whisper 1.1.1", "cache_paths": cache_paths, "pack_sha256": json.loads(LOCK.read_text(encoding="utf-8"))["pack_sha256"]}


def first_threshold_crossing(timeline: list[dict[str, Any]], threshold: float) -> float | None:
    return next((float(item["audio_timestamp_sec"]) for item in timeline if float(item["action_score"]) >= threshold), None)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w'-]+", text.lower(), flags=re.UNICODE)


def _levenshtein(left: list[str], right: list[str]) -> int:
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        next_row = [i]
        for j, b in enumerate(right, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (a != b)))
        row = next_row
    return row[-1]


def error_rates(reference: str, hypothesis: str, clip_aligned: bool) -> dict[str, float | None]:
    if not clip_aligned:
        return {"WER": None, "CER": None}
    words, output = _tokens(reference), _tokens(hypothesis)
    chars, out_chars = list("".join(words)), list("".join(output))
    return {"WER": round(_levenshtein(words, output) / max(1, len(words)), 4), "CER": round(_levenshtein(chars, out_chars) / max(1, len(chars)), 4)}


def redact(text: str) -> str:
    text = re.sub(r"\b[\d -]{12,}\b", "[REDACTED_NUMBER]", text)
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", text)
    return re.sub(r"\+?\d[\d ()-]{7,}\d", "[REDACTED_PHONE]", text)


def confusion_matrix(rows: list[dict[str, Any]], equivalence: str | None = None) -> dict[str, int]:
    result = {"TP": 0, "FP": 0, "FN": 0, "TN": 0}
    for row in rows:
        if not row.get("strict_score_eligible") or (equivalence and row.get("capture_equivalence") != equivalence):
            continue
        dangerous, triggered = row.get("expected_class") == "dangerous", bool(row.get("triggered"))
        result["TP" if dangerous and triggered else "FN" if dangerous else "FP" if triggered else "TN"] += 1
    return result


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def render(cm: dict[str, int]) -> dict[str, Any]:
        tp, fp, fn = cm["TP"], cm["FP"], cm["FN"]
        precision, recall = tp / (tp + fp) if tp + fp else None, tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
        return {**cm, "precision": round(precision, 4) if precision is not None else None, "recall": round(recall, 4) if recall is not None else None, "F1": round(f1, 4) if f1 is not None else None}
    return {"PRODUCTION_EQUIVALENT": render(confusion_matrix(rows, "PRODUCTION_EQUIVALENT")), "TWO_PARTY_STRESS_TEST": render(confusion_matrix(rows, "TWO_PARTY_STRESS_TEST")), "REAL_ONLY": render(confusion_matrix([x for x in rows if str(x.get("source_type", "")).startswith("REAL")])), "SYNTHETIC_ONLY": render(confusion_matrix([x for x in rows if x.get("source_type") == "SYNTHETIC"]))}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction + .999999)))], 4)


def asr_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wer = [float(row["whisper"]["WER"]) for row in rows if row.get("whisper", {}).get("WER") is not None]
    cer = [float(row["whisper"]["CER"]) for row in rows if row.get("whisper", {}).get("CER") is not None]
    whisper_latency = [float(value) for row in rows for value in row.get("performance", {}).get("utterance_end_to_whisper_sec", [])]
    nomic_latency = [float(value) for row in rows for value in row.get("performance", {}).get("utterance_end_to_nomic_sec", [])]
    return {"mean_WER": round(sum(wer) / len(wer), 4) if wer else None, "median_WER": percentile(wer, .5),
            "mean_CER": round(sum(cer) / len(cer), 4) if cer else None, "median_CER": percentile(cer, .5),
            "utterance_end_to_whisper_p50_sec": percentile(whisper_latency, .5), "utterance_end_to_whisper_p95_sec": percentile(whisper_latency, .95),
            "utterance_end_to_nomic_p50_sec": percentile(nomic_latency, .5), "utterance_end_to_nomic_p95_sec": percentile(nomic_latency, .95)}


class AudioReplayEngine:
    def __init__(self, preflight: dict[str, Any], logger: Callable[[str], None] = print):
        self.preflight, self.logger = preflight, logger
        from .nomic_deployment_v1 import NomicDeploymentV1
        self.nomic = NomicDeploymentV1()

    def replay(self, case: dict[str, Any], realtime: bool = False, *, quality_v2: bool = False) -> dict[str, Any]:
        """Authoritative replay: decode actual VAD-delimited PCM only once."""
        from .guarded_audio import transcribe_pcm_details
        from .realtime_pipeline import CALLER, CallerUtteranceBuffer, DualChannelPipeline
        from scripts.tail_aware_encoder import pack_turns

        raw, duration = load_pcm(Path(case["audio_path"]))
        buffer = CallerUtteranceBuffer(VAD_ENDPOINT_SILENCE_MS, MAX_UTTERANCE_MS)
        turns: list[tuple[str, str]] = []
        timeline: list[dict[str, Any]] = []
        utterances: list[dict[str, Any]] = []
        ui_events: list[dict[str, Any]] = []
        whisper_latencies: list[float] = []
        nomic_latencies: list[float] = []
        alert_announced = False
        threshold = float(self.preflight["threshold"])
        started = time.perf_counter()
        total_ms = round(duration * 1000)

        def process(final) -> None:
            nonlocal alert_announced
            # No language argument: each complete utterance performs fresh
            # Whisper language detection, including code-switching calls.
            def decode(pcm: bytes) -> dict[str, Any]:
                return transcribe_pcm_details(pcm, vad_filter=False, model_name="small", device="cuda", compute_type="float16")
            if quality_v2:
                from .whisper_quality import decode_with_optional_retry
                selection = decode_with_optional_retry(final.pcm, final.retry_pcm,
                                                       max(0.0, (final.end_ms - final.start_ms) / 1000), decode)
                details = selection["selected_details"]
                whisper_latency = float(selection["first_latency_sec"]) + float(selection["retry_latency_sec"] or 0.0)
            else:
                decode_started = time.perf_counter()
                details = decode(final.pcm)
                whisper_latency = time.perf_counter() - decode_started
                selection = {"retry_occurred": False, "retry_reason": None, "selected": "first", "selection_reason": "baseline_single_decode",
                             "first": details, "retry": None, "first_latency_sec": round(whisper_latency, 4), "retry_latency_sec": None}
            whisper_latencies.append(whisper_latency)
            text = str(details.get("text", "")).strip()
            utterance = {"audio_start_sec": round(final.start_ms / 1000, 3), "audio_end_sec": round(final.end_ms / 1000, 3),
                         "finalization_reason": final.reason, "text": redact(text), "language": details.get("language"),
                         "language_probability": details.get("languageProbability"), "segments": details.get("segments", []),
                         "transcription_latency_sec": round(whisper_latency, 4), "audio_bytes": len(final.pcm),
                         "retry_audio_bytes": len(final.retry_pcm), "retry_occurred": selection["retry_occurred"],
                         "retry_reason": selection["retry_reason"], "selected": selection["selected"],
                         "selection_reason": selection["selection_reason"], "first_decode": selection["first"],
                         "retry_decode": selection["retry"], "first_decode_latency_sec": selection["first_latency_sec"],
                         "retry_decode_latency_sec": selection["retry_latency_sec"]}
            utterances.append(utterance)
            if not text:
                return
            turns.append((CALLER, text))
            ui_events.append({"type": "FINAL_TRANSCRIPT", "speaker": CALLER, "text": redact(text),
                              "audio_start_sec": utterance["audio_start_sec"], "audio_end_sec": utterance["audio_end_sec"]})
            nomic_input = pack_turns(turns, self.nomic.adapter.tokenizer, 384)
            nomic_started = time.perf_counter()
            signal = self.nomic.score(list(turns))
            nomic_latency = time.perf_counter() - nomic_started
            nomic_latencies.append(nomic_latency)
            row = {"audio_timestamp_sec": utterance["audio_end_sec"], "transcript": redact(text),
                   "rolling_transcript": redact(" ".join(item for _, item in turns)), "committed_transcript": redact(" ".join(item for _, item in turns)),
                   "finalization_reason": final.reason, "token_count": len(_tokens(" ".join(item for _, item in turns))),
                   "nomic_input": nomic_input, "nomic_token_count": len(self.nomic.adapter.tokenizer(nomic_input, add_special_tokens=True)["input_ids"]),
                   "action_score": signal.action_score, "semantic_scores": signal.semantic_scores, "kind_scores": signal.kind_scores,
                   "threshold": threshold, "dangerous": signal.action_score >= threshold, "inference_latency_sec": round(nomic_latency, 4),
                   "utterance_end_to_whisper_sec": round(whisper_latency, 4), "utterance_end_to_nomic_sec": round(whisper_latency + nomic_latency, 4),
                   "model_input_hash": hashlib.sha256(nomic_input.encode("utf-8")).hexdigest().upper()}
            timeline.append(row)
            self.logger(f"[{final.end_ms / 1000:05.1f}] FINAL_TRANSCRIPT\n{utterance['text']}")
            self.logger(f"[{final.end_ms / 1000:05.1f}] NOMIC\nscore={signal.action_score:.4f}\nthreshold={threshold:.2f}\ndangerous={row['dangerous']}")
            if row["dangerous"] and not alert_announced:
                alert_announced = True
                self.logger(f"[{final.end_ms / 1000:05.1f}] ALERT FIRST_THRESHOLD_CROSSING")

        for offset in range(0, max(1, total_ms), VAD_FRAME_MS):
            end = min(total_ms, offset + VAD_FRAME_MS)
            frame = raw[offset * PCM_RATE // 1000 * 4:end * PCM_RATE // 1000 * 4]
            if realtime:
                time.sleep(max(0, (end - offset) / 1000))
            for final in buffer.ingest(frame, offset, end, voiced=DualChannelPipeline.has_speech(frame)):
                process(final)
        for final in buffer.finish(total_ms):
            process(final)
        final_transcript = " ".join(text for _, text in turns)
        crossing = first_threshold_crossing(timeline, threshold)
        rates = error_rates(case.get("reference_transcript", ""), final_transcript, bool(case.get("reference_transcript_clip_aligned")))
        return {**case, "pipeline_version": WHISPER_QUALITY_V2_PIPELINE_VERSION if quality_v2 else UTTERANCE_PIPELINE_VERSION, "duration_sec": duration,
                "status": "PASS" if (case["expected_class"] == "dangerous") == bool(crossing is not None) else "FAIL_DETECTION",
                "triggered": crossing is not None, "first_alert_sec": crossing,
                "whisper": {"final_transcript": redact(final_transcript), "utterances": utterances, "segments": len(utterances),
                            "latency_sec": round(sum(whisper_latencies), 4), "real_time_factor": round(sum(whisper_latencies) / max(duration, .001), 4), **rates},
                "segmentation": {"vad_frame_ms": VAD_FRAME_MS, "endpoint_silence_ms": VAD_ENDPOINT_SILENCE_MS,
                                 "max_utterance_ms": MAX_UTTERANCE_MS, "rationale": "750 ms preserves common natural pauses; 12 s caps continuous speech without short overlap windows."},
                "nomic": {"timeline": timeline, "max_score": max((item["action_score"] for item in timeline), default=None),
                          "final_score": timeline[-1]["action_score"] if timeline else None, "threshold": threshold},
                "ui_events": ui_events,
                "alert": {"triggered": crossing is not None, "first_alert_sec": crossing,
                          "first_alert_reason": "FIRST_THRESHOLD_CROSSING" if crossing is not None else None},
                "performance": {"end_to_end_sec": round(time.perf_counter() - started, 4),
                                "utterance_end_to_whisper_sec": [round(value, 4) for value in whisper_latencies],
                                "utterance_end_to_nomic_sec": [round(left + right, 4) for left, right in zip(whisper_latencies, nomic_latencies)]}, "errors": []}

    def replay_whisper_quality_v2(self, case: dict[str, Any], realtime: bool = False) -> dict[str, Any]:
        """Whole-utterance V2: one selected final transcript per utterance."""
        return self.replay(case, realtime, quality_v2=True)

    def replay_streaming(self, case: dict[str, Any], realtime: bool = False) -> dict[str, Any]:
        from .guarded_audio import transcribe_pcm_details
        from .realtime_pipeline import CALLER, DualChannelPipeline
        raw, duration = load_pcm(Path(case["audio_path"]))
        whisper_latencies: list[float] = []
        languages: list[str] = []
        def transcribe(chunk: bytes) -> dict[str, Any]:
            started = time.perf_counter()
            details = transcribe_pcm_details(chunk, vad_filter=False, model_name="small", device="cuda", compute_type="float16")
            whisper_latencies.append(time.perf_counter() - started)
            languages.append(str(details["language"]))
            return details
        pipeline, timeline, whisper_windows = DualChannelPipeline(transcribe), [], []
        alert_announced = False
        threshold = float(self.preflight["threshold"])
        started = time.perf_counter()
        total_ms = round(duration * 1000)
        for offset in range(0, max(1, total_ms), STRIDE_MS):
            end = min(total_ms, offset + WINDOW_MS)
            chunk = raw[offset * PCM_RATE // 1000 * 4:end * PCM_RATE // 1000 * 4]
            if realtime:
                time.sleep(max(0, (end - offset) / 1000))
            if pipeline.ingest(CALLER, chunk, offset, end):
                event = pipeline.drain_streaming_once(end_of_stream=end >= total_ms)
                if event is None:
                    continue
                raw_window = {"audio_start_sec": round(offset / 1000, 3), "audio_end_sec": round(end / 1000, 3),
                              "raw_text": redact(str(event.metadata.get("text", ""))), "language": event.metadata.get("language"),
                              "language_probability": event.metadata.get("languageProbability"), "average_logprob": event.metadata.get("averageLogProb"),
                              "no_speech_probability": event.metadata.get("noSpeechProbability"), "segments": event.metadata.get("segments", []),
                              "stabilizer_action": event.action, "stabilizer_reason": event.reason,
                              "provisional_text": redact(event.provisional_text or ""), "committed_text": redact(event.committed_text or ""),
                              "finalization_reason": event.finalization_reason, "overlap_evidence": event.metadata.get("overlap_evidence")}
                whisper_windows.append(raw_window)
                self.logger(f"[{end / 1000:05.1f}] WHISPER\n{raw_window['raw_text']}")
                self.logger(f"[{end / 1000:05.1f}] STABILIZER\naction={event.action}\nreason={event.reason}\nprovisional={raw_window['provisional_text']}\ncommitted={raw_window['committed_text']}\nfinalization={event.finalization_reason}")
                stabilizer = pipeline.streaming_stabilizers[CALLER]
                if event.analysis_text_changed:
                    turns = stabilizer.nomic_turns(CALLER)
                    from scripts.tail_aware_encoder import pack_turns
                    nomic_input = pack_turns(turns, self.nomic.adapter.tokenizer, 384)
                    nomic_started = time.perf_counter(); signal = self.nomic.score(turns); latency = time.perf_counter() - nomic_started
                    row = {"audio_timestamp_sec": round(end / 1000, 3), "stabilizer_action": event.action, "transcript": event.provisional_text or event.committed_text or "", "rolling_transcript": " ".join(text for _, text in turns), "committed_transcript": stabilizer.committed_transcript, "provisional_text": stabilizer.provisional_text, "token_count": len(_tokens(" ".join(text for _, text in turns))), "nomic_input": nomic_input, "nomic_token_count": len(self.nomic.adapter.tokenizer(nomic_input, add_special_tokens=True)["input_ids"]), "action_score": signal.action_score, "semantic_scores": signal.semantic_scores, "kind_scores": signal.kind_scores, "threshold": threshold, "dangerous": signal.action_score >= threshold, "inference_latency_sec": round(latency, 4), "model_input_hash": hashlib.sha256(nomic_input.encode("utf-8")).hexdigest().upper()}
                    timeline.append(row)
                    self.logger(f"[{end / 1000:05.1f}] NOMIC\nscore={signal.action_score:.4f}\nthreshold={threshold:.2f}\ndangerous={row['dangerous']}\ntoken_count={row['nomic_token_count']}\ninput_hash={row['model_input_hash']}\ninput={nomic_input}")
                    if row["dangerous"] and not alert_announced:
                        alert_announced = True
                        self.logger(f"[{end / 1000:05.1f}] ALERT FIRST_THRESHOLD_CROSSING")
        final_transcript = pipeline.streaming_stabilizers[CALLER].committed_transcript
        crossing = first_threshold_crossing(timeline, threshold)
        rates = error_rates(case.get("reference_transcript", ""), final_transcript, bool(case.get("reference_transcript_clip_aligned")))
        return {**case, "pipeline_version": STREAMING_PIPELINE_VERSION, "duration_sec": duration, "status": "PASS" if (case["expected_class"] == "dangerous") == bool(crossing is not None) else "FAIL_DETECTION", "triggered": crossing is not None, "first_alert_sec": crossing, "whisper": {"final_transcript": redact(final_transcript), "raw_detected_languages": sorted(set(languages)), "windows": whisper_windows, "segments": len(pipeline.metrics), "latency_sec": round(sum(whisper_latencies), 4), "real_time_factor": round(sum(whisper_latencies) / max(duration, .001), 4), **rates}, "nomic": {"timeline": timeline, "max_score": max((x["action_score"] for x in timeline), default=None), "final_score": timeline[-1]["action_score"] if timeline else None, "threshold": threshold}, "alert": {"triggered": crossing is not None, "first_alert_sec": crossing, "first_alert_reason": "FIRST_THRESHOLD_CROSSING" if crossing is not None else None}, "performance": {"end_to_end_sec": round(time.perf_counter() - started, 4)}, "errors": []}


def write_reports(results: list[dict[str, Any]], preflight: dict[str, Any], run_id: str, reports_dir: Path = REPORTS, artifact_stem: str = "SCUT_AUDIO_REPLAY_V1", pipeline_version: str | None = None) -> dict[str, str]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    summary = {"run_id": run_id, "created_at": now(), "pipeline_version": pipeline_version, "provenance": preflight, "integrity_limitations": "This Audio Replay Pack is an end-to-end engineering evaluation (audio → Whisper → Nomic), not an untouched scientific fresh benchmark. Public internet audio can have appeared in foundation-model pretraining.", "metrics": metrics(results), "asr_metrics": asr_summary(results), "calls": results}
    json_path, csv_path, md_path = reports_dir / f"{artifact_stem}_RESULTS.json", reports_dir / f"{artifact_stem}_RESULTS.csv", reports_dir / f"{artifact_stem}_REPORT.md"
    atomic_json_write(json_path, summary)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "source_type", "language", "expected_class", "strict_score_eligible", "capture_equivalence", "status", "triggered", "first_alert_sec", "max_score", "WER", "CER"])
        writer.writeheader()
        for row in results:
            writer.writerow({"case_id": row["case_id"], "source_type": row["source_type"], "language": row["language"], "expected_class": row["expected_class"], "strict_score_eligible": row["strict_score_eligible"], "capture_equivalence": row["capture_equivalence"], "status": row["status"], "triggered": row["triggered"], "first_alert_sec": row["first_alert_sec"], "max_score": row["nomic"]["max_score"], "WER": row["whisper"]["WER"], "CER": row["whisper"]["CER"]})
    m = summary["metrics"]
    languages = {language: [row for row in results if row["language"] == language] for language in sorted({row["language"] for row in results})}
    def median(values: list[float]) -> float | None:
        return round(sorted(values)[len(values) // 2], 4) if values else None
    alerts = [row["first_alert_sec"] for row in results if row["expected_class"] == "dangerous" and row["first_alert_sec"] is not None]
    whisper_rtf = [row["whisper"]["real_time_factor"] for row in results]
    nomic_latency = [event["inference_latency_sec"] for row in results for event in row["nomic"]["timeline"]]
    failures = [row for row in results if row["status"] != "PASS"]
    table = "\n".join(f"| {row['case_id']} | {row['source_type']} | {row['language']} | {row['expected_class']} | {row['status']} | {row['first_alert_sec'] if row['first_alert_sec'] is not None else 'N/A'} |" for row in results)
    md = f"""# {artifact_stem}

## Executive result

This Audio Replay Pack is an end-to-end engineering evaluation: audio → Whisper → Nomic. It is not an untouched scientific fresh benchmark.

## Source pack

- Prepared: {len(results)}; real: {sum(row['source_type'].startswith('REAL') for row in results)}; synthetic: {sum(row['source_type'] == 'SYNTHETIC' for row in results)}.
- Strict-score eligible: {sum(bool(row['strict_score_eligible']) for row in results)}. External candidates remained `REFERENCE_ONLY` or `OPTIONAL_UNVERIFIED_SOURCE` and were not replayed.
- Languages: {', '.join(f'{key}={len(value)}' for key, value in languages.items())}.

## Whisper

- RTF p50: {median(whisper_rtf)}. WER/CER are populated only for clip-aligned synthetic scripts.
- Mean/median WER: {summary['asr_metrics']['mean_WER']} / {summary['asr_metrics']['median_WER']}; mean/median CER: {summary['asr_metrics']['mean_CER']} / {summary['asr_metrics']['median_CER']}.

## Nomic after Whisper

```json
{json.dumps(m, indent=2)}
```

## Real-only result

```json
{json.dumps(m['REAL_ONLY'], indent=2)}
```

## Synthetic-only result

```json
{json.dumps(m['SYNTHETIC_ONLY'], indent=2)}
```

## Language result

{json.dumps({key: {'cases': len(value), 'triggered': sum(bool(row['triggered']) for row in value)} for key, value in languages.items()}, indent=2)}

## Time to alert and performance

- Alert time p50: {median(alerts)} seconds; alert observations: {len(alerts)}.
- Nomic inference latency p50: {median(nomic_latency)} seconds.
- Utterance-end → Whisper p50/p95: {summary['asr_metrics']['utterance_end_to_whisper_p50_sec']} / {summary['asr_metrics']['utterance_end_to_whisper_p95_sec']} seconds.
- Utterance-end → Nomic p50/p95: {summary['asr_metrics']['utterance_end_to_nomic_p50_sec']} / {summary['asr_metrics']['utterance_end_to_nomic_p95_sec']} seconds.
- Hardware label: RTX5070_DEVELOPMENT_MACHINE. These are not TUF results.

## Failed cases

{json.dumps([{'case_id': row['case_id'], 'status': row['status'], 'expected_class': row['expected_class'], 'max_score': row['nomic']['max_score']} for row in failures], indent=2)}

## Individual call table

| Case | Type | Language | Expected | Status | First alert sec |
| --- | --- | --- | --- | --- | --- |
{table}

## Source / usage notes

See `data/audio_replay_v1/source_manifest.json`; raw third-party media was not committed or used.

## Integrity limitations

{summary['integrity_limitations']}
"""
    md_path.write_text(md, encoding="utf-8")
    return {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)}
