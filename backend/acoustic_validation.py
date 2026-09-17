"""Offline acoustic fixture validation for the production caller ASR path.

This module deliberately contains no risk classification or capture code.  It
creates diagnostics-only WAV files, streams each one through the same 2 s / 1
s caller windows used by FAST ASR, and records semantic evidence rather than
pretending that a word-error-rate is a safety result.
"""
from __future__ import annotations

from dataclasses import asdict
import audioop
from array import array
import json
import math
from pathlib import Path
import random
import re
import time
import wave
from typing import Callable

from .dual_pass_asr import ASRText, DualPassCallerASR
from .realtime_pipeline import CALLER, DualChannelPipeline

RATE = 48_000
WINDOW_MS, STRIDE_MS = 2_000, 1_000

# Text is deliberately ordinary Unicode, not the mojibake that can result when
# a UTF-8 requirements document is opened with a legacy Windows code page.
PHRASES = (
    ("ru", "dangerous", "Назовите код из SMS.", ("intent", "action", "target")),
    ("ru", "dangerous", "Сейчас вам придёт код, продиктуйте его мне.", ("intent", "action", "target")),
    ("ru", "dangerous", "Срочно переведите деньги на безопасный счёт.", ("action", "target", "urgency")),
    ("ru", "dangerous", "Установите AnyDesk, чтобы я мог вам помочь.", ("action", "remote_access")),
    ("ru", "dangerous", "Назовите PIN-код карты.", ("intent", "action", "target")),
    ("ru", "dangerous", "Продиктуйте CVV с обратной стороны карты.", ("intent", "action", "target")),
    ("ru", "dangerous", "Назовите пароль от интернет-банка.", ("intent", "action", "target")),
    ("ru", "dangerous", "Сообщите seed phrase от вашего кошелька.", ("intent", "action", "target")),
    ("ru", "dangerous", "Ваш сын попал в аварию, срочно нужны деньги.", ("target", "urgency")),
    ("ru", "protective", "Никому не называйте код из SMS.", ("negation", "protective", "target")),
    ("ru", "protective", "Не сообщайте PIN-код никому.", ("negation", "protective", "target")),
    ("ru", "protective", "Никогда не устанавливайте AnyDesk по просьбе незнакомца.", ("negation", "protective", "remote_access")),
    ("ru", "context", "Я сотрудник банка.", ("intent",)),
    ("ru", "context", "По вашей карте подозрительная операция.", ("target",)),
    ("ru", "context", "Я звоню из службы безопасности.", ("intent",)),
    ("en", "dangerous", "Tell me the code from the SMS.", ("intent", "action", "target")),
    ("en", "protective", "Do not share the SMS code with anyone.", ("negation", "protective", "target")),
    ("en", "context", "I am calling from the bank security department.", ("intent",)),
    ("ro", "dangerous", "Spune-mi codul primit prin SMS.", ("intent", "action", "target")),
    ("ro", "protective", "Nu spune nimănui codul primit prin SMS.", ("negation", "protective", "target")),
    ("ro", "context", "Sunt angajat al băncii.", ("intent",)),
)

TOKENS = {
    "intent": {"ru": ("назов", "продикт", "сообщ", "сотрудник", "звон"), "en": ("tell", "calling"), "ro": ("spune", "angajat")},
    "action": {"ru": ("назов", "продикт", "перевед", "установ"), "en": ("tell",), "ro": ("spune",)},
    "target": {"ru": ("код", "sms", "смс", "деньг", "счёт", "счет", "pin", "cvv", "парол", "карт", "seed", "кошел"), "en": ("code", "sms"), "ro": ("cod", "sms")},
    "negation": {"ru": ("не", "никому", "никогда"), "en": ("not", "never", "anyone"), "ro": ("nu", "nimănui")},
    "protective": {"ru": ("не", "никому", "никогда"), "en": ("not", "anyone"), "ro": ("nu", "nimănui")},
    "urgency": {"ru": ("срочно",), "en": ("urgent",), "ro": ("urgent",)},
    "remote_access": {"ru": ("anydesk",), "en": ("anydesk",), "ro": ("anydesk",)},
}

def semantic_fields(text: str, language: str, required: tuple[str, ...]) -> dict[str, bool]:
    lower = text.lower()
    return {field: any(token in lower for token in TOKENS[field][language]) for field in required}

def has_explicit_negation(text: str, language: str) -> bool:
    """Polarity-only negation check, kept distinct from recall-oriented fields."""
    tokens = "|".join(re.escape(token) for token in TOKENS["negation"][language])
    return bool(re.search(rf"(?<!\w)(?:{tokens})(?!\w)", text, flags=re.IGNORECASE))

def polarity_inversion(text: str, language: str, expected_semantic_class: str) -> str | None:
    """Report a true SAFE/DANGEROUS polarity flip without changing acceptance."""
    negative = has_explicit_negation(text, language)
    if expected_semantic_class == "dangerous" and negative:
        return "SAFE_INSTEAD_OF_DANGEROUS"
    if expected_semantic_class == "protective" and text.strip() and not negative:
        return "DANGEROUS_INSTEAD_OF_SAFE"
    return None

def make_degraded_pcm(pcm: bytes, variant: str) -> tuple[bytes, int, int]:
    """Return PCM16 audio; degradation remains intelligible and deterministic."""
    if variant == "clean": return pcm, RATE, 2
    mono = audioop.tomono(pcm, 2, .5, .5)
    if variant == "mono16k": return audioop.ratecv(mono, 2, 1, RATE, 16_000, None)[0], 16_000, 1
    samples = list(memoryview(mono).cast("h")); out: list[int] = []
    # A modest first-order ~telephone band; high-pass is implemented as a
    # difference and low-pass as a stable IIR.  It avoids optional DSP deps.
    previous = low = 0.0; rng = random.Random(104729)
    for sample in samples:
        high = sample - previous; previous = sample
        low += .32 * (high - low)
        if variant in {"telephone", "telephone_noise", "compressed"}: value = low
        else: value = sample
        if variant == "telephone_noise": value += rng.gauss(0, 260)
        if variant == "low_level": value *= .38
        if variant == "compressed": value = math.tanh(value / 8500.0) * 9200
        out.append(max(-32768, min(32767, int(value))))
    return array("h", out).tobytes(), RATE, 1

def write_wav(path: Path, pcm: bytes, rate: int, channels: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels); handle.setsampwidth(2); handle.setframerate(rate); handle.writeframes(pcm)

def wav_to_guarded_pcm(path: Path) -> tuple[bytes, int]:
    """Normalise a fixture to the raw 48 kHz stereo format of guarded capture."""
    with wave.open(str(path), "rb") as handle:
        raw, rate, channels, width = handle.readframes(handle.getnframes()), handle.getframerate(), handle.getnchannels(), handle.getsampwidth()
    if width != 2: raise ValueError(f"PCM16 required: {path}")
    if channels == 1: raw = audioop.tostereo(raw, 2, 1, 1)
    elif channels != 2: raise ValueError(f"mono/stereo required: {path}")
    if rate != RATE: raw = audioop.ratecv(raw, 2, 2, rate, RATE, None)[0]
    return raw, round(len(raw) / (RATE * 4) * 1000)

def stream_fast(pcm: bytes, transcribe: Callable[[bytes], str]) -> tuple[list[dict], str, list[dict]]:
    """Exact caller pipeline: VAD gate, priority queue, 2s/1s windows, revisions."""
    pipeline = DualChannelPipeline(transcribe)
    timeline: list[dict] = []
    total_ms = round(len(pcm) / (RATE * 4) * 1000)
    for start in range(0, max(1, total_ms), STRIDE_MS):
        end = min(total_ms, start + WINDOW_MS)
        frame = pcm[start * RATE // 1000 * 4:end * RATE // 1000 * 4]
        queued = pipeline.ingest(CALLER, frame, start, end)
        if queued:
            turn = pipeline.drain_once(utterance_closed=end >= total_ms)
            partial = pipeline.stabilizers[CALLER].partial
            timeline.append({"startMs": start, "endMs": end, "partial": partial, "emitted": turn.text if turn else "", "backlog": pipeline.scheduler.caller.qsize()})
    return timeline, pipeline.stabilizers[CALLER].stable or pipeline.stabilizers[CALLER].partial, pipeline.metrics

def report_case(case_id: str, language: str, semantic_class: str, source: str, wav: Path,
                fast: Callable[[bytes], str], accurate: Callable[[bytes], ASRText]) -> dict:
    pcm, duration_ms = wav_to_guarded_pcm(wav)
    first_decode_started = time.perf_counter()
    timeline, final_fast, metrics = stream_fast(pcm, fast)
    elapsed = time.perf_counter() - first_decode_started
    required = next(row[3] for row in PHRASES if row[0:3] == (language, semantic_class, source))
    semantic_at = next((row["endMs"] for row in timeline if all(semantic_fields(row["partial"], language, required).values())), None)
    # The accurate pass uses its production safe-gap scheduler, after FAST is drained.
    accurate_runner = DualPassCallerASR(lambda raw: ASRText(fast(raw)), accurate)
    accurate_runner.submit_accurate_caller(pcm, 0, duration_ms); accurate_runner.set_safe_gap(True)
    stable = accurate_runner.drain_once()
    fast_fields = semantic_fields(final_fast, language, required)
    accurate_text = stable.text if stable else ""
    accurate_fields = semantic_fields(accurate_text, language, required)
    failure = []
    if not all(fast_fields.values()): failure.append("missing semantic fields: " + ", ".join(k for k,v in fast_fields.items() if not v))
    if semantic_class == "protective" and not fast_fields.get("negation", False): failure.append("CRITICAL: meaning-changing negation lost")
    if any(row["backlog"] for row in timeline): failure.append("caller backlog observed")
    return {"id": case_id, "language": language, "variant": wav.stem.rsplit("__", 1)[-1], "expectedSemanticClass": semantic_class,
            "sourceText": source, "phraseDurationMs": duration_ms, "fastTranscriptTimeline": timeline, "fastFinalTranscript": final_fast,
            "accurateTranscript": accurate_text, "fastSemanticFields": fast_fields, "accurateSemanticFields": accurate_fields,
            "negationPreserved": fast_fields.get("negation") if "negation" in required else None,
            "firstPartialMs": timeline[0]["endMs"] if timeline and timeline[0]["partial"] else None,
            "usefulSemanticLatencyMs": semantic_at, "fastDecodeSeconds": round(elapsed, 3), "rtf": round(elapsed / max(.001, duration_ms/1000), 3),
            "backlogMax": max((row["backlog"] for row in timeline), default=0), "pass": not failure, "failureReason": "; ".join(failure) or None}

def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
