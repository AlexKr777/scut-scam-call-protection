"""Serialized dual-pass caller ASR scheduling.

FAST partials are the only work allowed on the critical caller path.  The
accurate pass is deliberately admitted only in a declared safe gap, so it can
never be the work that an arriving FAST caller item waits behind.
"""
from __future__ import annotations

from dataclasses import dataclass
import queue
import time
from typing import Callable

from .realtime_pipeline import CALLER, USER, Utterance, ConversationAssembler, overlap_deduplicate


@dataclass
class ASRText:
    text: str
    language: str = "und"
    language_probability: float = 0.0
    # Optional decoder facts.  Keeping these separate from text prevents a
    # downstream finalizer from mistaking an unsupported string for evidence.
    evidence: dict = None


@dataclass
class FastPartial:
    speaker: str
    text: str
    start_ms: int
    end_ms: int
    revision_id: int
    stable: bool = False
    language: str = "und"
    language_probability: float = 0.0
    quality: str = "FAST"


@dataclass
class ASRWork:
    speaker: str
    pcm: bytes
    start_ms: int
    end_ms: int
    kind: str  # FAST or ACCURATE


class DualPassScheduler:
    """Bounded queues and one CPU inference lane.

    `safe_gap` is set only after caller VAD has closed an utterance and capture
    confirms no new caller speech is pending. Accurate jobs otherwise remain
    queued; caller FAST always wins. This avoids competing CPU-heavy models.
    """
    def __init__(self, max_items: int = 24):
        self.fast_caller: queue.Queue[ASRWork] = queue.Queue(max_items)
        self.fast_user: queue.Queue[ASRWork] = queue.Queue(max_items)
        self.accurate: queue.Queue[ASRWork] = queue.Queue(max_items)
        self.safe_gap = False
        self.dropped = {"FAST_CALLER": 0, "FAST_USER": 0, "ACCURATE": 0}

    def submit(self, item: ASRWork) -> bool:
        target = self.fast_caller if item.kind == "FAST" and item.speaker == CALLER else self.fast_user if item.kind == "FAST" else self.accurate
        try:
            target.put_nowait(item)
            return True
        except queue.Full:
            # Bounded freshness: retain the newest item of its class.
            try:
                target.get_nowait()
            except queue.Empty:
                return False
            key = "FAST_CALLER" if target is self.fast_caller else "FAST_USER" if target is self.fast_user else "ACCURATE"
            self.dropped[key] += 1
            target.put_nowait(item)
            return True

    def next(self) -> ASRWork | None:
        for target in (self.fast_caller, self.fast_user):
            try:
                return target.get_nowait()
            except queue.Empty:
                pass
        # Accurate decoding is never admitted while capture is active unless
        # the VAD/capture stage has explicitly declared a safe gap.
        if self.safe_gap:
            try:
                return self.accurate.get_nowait()
            except queue.Empty:
                pass
        return None

    def backlog(self) -> dict[str, int]:
        return {"fastCaller": self.fast_caller.qsize(), "fastUser": self.fast_user.qsize(), "accurate": self.accurate.qsize()}


class DualPassCallerASR:
    """Model-independent orchestration; model functions are injected for tests/runtime."""
    def __init__(self, fast_transcribe: Callable[[bytes], ASRText], accurate_transcribe: Callable[[bytes], ASRText], on_fast_partial: Callable[[FastPartial], None] | None = None):
        self.fast_transcribe = fast_transcribe
        self.accurate_transcribe = accurate_transcribe
        self.on_fast_partial = on_fast_partial
        self.scheduler = DualPassScheduler()
        self.assembler = ConversationAssembler()
        self.fast_partial: FastPartial | None = None
        self._revision = 0
        self._fast_aggregate = ""
        self.metrics: list[dict] = []
        self.timeline: dict[str, float | None] = {"speech_semantics_available_at": None, "fast_partial_ready_at": None, "stable_text_ready_at": None, "future_ai_request_ready_at": None}

    def submit_fast(self, speaker: str, pcm: bytes, start_ms: int, end_ms: int) -> bool:
        return self.scheduler.submit(ASRWork(speaker, pcm, start_ms, end_ms, "FAST"))

    def submit_accurate_caller(self, pcm: bytes, start_ms: int, end_ms: int) -> bool:
        return self.scheduler.submit(ASRWork(CALLER, pcm, start_ms, end_ms, "ACCURATE"))

    def set_safe_gap(self, active: bool) -> None:
        self.scheduler.safe_gap = active

    def drain_once(self) -> FastPartial | Utterance | None:
        work = self.scheduler.next()
        if not work:
            return None
        started = time.monotonic()
        if work.kind == "FAST":
            result = self.fast_transcribe(work.pcm)
            self._revision += 1
            partial = FastPartial(work.speaker, result.text.strip(), work.start_ms, work.end_ms, self._revision,
                                  False, result.language, result.language_probability)
            self.fast_partial = partial
            ready=time.monotonic()
            if partial.speaker == CALLER and partial.text:
                self.timeline["speech_semantics_available_at"] = ready
                self.timeline["fast_partial_ready_at"] = ready
                self.timeline["future_ai_request_ready_at"] = ready
                if self.on_fast_partial:
                    self.on_fast_partial(partial)
            self.metrics.append({"kind": "FAST", "speaker": work.speaker, "decodeMs": round((ready-started)*1000, 1), "backlog": self.scheduler.backlog(), "fastPartialReadyAt": ready})
            return partial if partial.text else None
        result = self.accurate_transcribe(work.pcm)
        # Accurate text is authoritative; one completed utterance, never a
        # sequence of FAST revisions appended to conversation history.
        stable = overlap_deduplicate("", result.text.strip())
        turn = self.assembler.emit(CALLER, stable, work.start_ms, work.end_ms,
                                   {"source": "ACCURATE", "language": result.language, "languageProbability": result.language_probability})
        ready=time.monotonic(); self.timeline["stable_text_ready_at"] = ready
        self.metrics.append({"kind": "ACCURATE", "speaker": CALLER, "decodeMs": round((ready-started)*1000, 1), "backlog": self.scheduler.backlog(), "stableTextReadyAt": ready})
        return turn


def projected_warning_latency(semantics_at: float, fast_ready_at: float, stable_ready_at: float) -> dict[str, float]:
    """Future network-only addition; no AnyModel call is made here."""
    fast_delay = max(0.0, fast_ready_at - semantics_at)
    stable_delay = max(0.0, stable_ready_at - semantics_at)
    return {"fastPathSeconds": round(fast_delay, 3), "stablePathSeconds": round(stable_delay, 3),
            **{f"futureAi{seconds:.1f}s": round(fast_delay + seconds, 3) for seconds in (.5, 1., 2., 3.)}}
