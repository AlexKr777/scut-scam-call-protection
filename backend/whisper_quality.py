"""ASR-only quality policy for one finalized Whisper utterance."""
from __future__ import annotations

import re
import time
from collections import Counter
from typing import Any, Callable


def _number(details: dict[str, Any], key: str, default: float) -> float:
    try:
        value = details.get(key)
        return default if value in {None, ""} else float(value)
    except (TypeError, ValueError):
        return default


def _words(text: str) -> list[str]:
    return re.findall(r"[\w'-]+", text.lower(), re.UNICODE)


def _pathological_repetition(text: str) -> bool:
    words = _words(text)
    return len(words) >= 4 and max(Counter(words).values()) / len(words) >= 0.6


def retry_reason(details: dict[str, Any], duration_sec: float) -> str | None:
    """Return a conservative Whisper-native reason, never a downstream score."""
    text = " ".join(str(details.get("text", "")).split())
    average_logprob = _number(details, "averageLogProb", 0.0)
    no_speech = _number(details, "noSpeechProbability", 0.0)
    compression = _number(details, "compressionRatio", 0.0)
    words = _words(text)
    if not text and duration_sec >= 0.75:
        return "empty_meaningful_audio"
    if average_logprob <= -1.0:
        return "low_average_logprob"
    if no_speech >= 0.60:
        return "high_no_speech_probability"
    if compression >= 2.6:
        return "high_compression_ratio"
    if duration_sec >= 3.0 and len(words) <= 1:
        return "implausibly_short_transcript"
    return None


def _quality_score(details: dict[str, Any], duration_sec: float) -> float:
    text = " ".join(str(details.get("text", "")).split())
    if not text:
        return -100.0
    score = _number(details, "averageLogProb", -5.0)
    score -= _number(details, "noSpeechProbability", 1.0)
    compression = _number(details, "compressionRatio", 10.0)
    if compression >= 2.6:
        score -= 10.0
    if _pathological_repetition(text):
        score -= 10.0
    if duration_sec >= 3.0 and len(_words(text)) <= 1:
        score -= 2.0
    return score


def _decode(pcm: bytes, transcribe: Callable[[bytes], dict[str, Any]]) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    details = dict(transcribe(pcm))
    return details, time.perf_counter() - started


def decode_with_optional_retry(first_pcm: bytes, retry_pcm: bytes, duration_sec: float,
                               transcribe: Callable[[bytes], dict[str, Any]]) -> dict[str, Any]:
    """Decode once, retry one suspicious utterance, and choose one ASR-only result."""
    first, first_latency = _decode(first_pcm, transcribe)
    reason = retry_reason(first, duration_sec)
    result: dict[str, Any] = {
        "first": first, "retry": None, "retry_occurred": bool(reason), "retry_reason": reason,
        "first_latency_sec": round(first_latency, 4), "retry_latency_sec": None,
    }
    if not reason:
        result.update({"selected": "first", "text": " ".join(str(first.get("text", "")).split()),
                       "selected_details": first, "selection_reason": "first_decode_not_suspicious"})
        return result
    retry, retry_latency = _decode(retry_pcm, transcribe)
    first_score, retry_score = _quality_score(first, duration_sec), _quality_score(retry, duration_sec)
    selected = "retry" if retry_score > first_score else "first"
    selected_details = retry if selected == "retry" else first
    result.update({"retry": retry, "retry_latency_sec": round(retry_latency, 4), "selected": selected,
                   "text": " ".join(str(selected_details.get("text", "")).split()),
                   "selected_details": selected_details,
                   "selection_reason": "retry_candidate_higher_asr_quality" if selected == "retry" else "first_candidate_higher_asr_quality",
                   "first_quality_score": round(first_score, 4), "retry_quality_score": round(retry_score, 4)})
    return result
