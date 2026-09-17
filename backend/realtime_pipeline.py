"""Priority dual-channel conversation pipeline. Audio capture is deliberately outside ASR/analysis workers."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from collections import deque
import queue
import re
import time
import uuid
import audioop
from typing import Any, Callable, Iterable, Mapping

CALLER = "CALLER"
USER = "USER"

@dataclass
class Timing:
    audio_received_at: float
    speech_detected_at: float | None = None
    asr_started_at: float | None = None
    partial_ready_at: float | None = None
    stable_text_ready_at: float | None = None
    utterance_finalized_at: float | None = None
    risk_analysis_started_at: float | None = None
    risk_analysis_completed_at: float | None = None
    alert_ready_at: float | None = None

@dataclass
class AudioWork:
    speaker: str
    pcm: bytes
    start_ms: int
    end_ms: int
    timing: Timing


@dataclass(frozen=True)
class FinalAudioUtterance:
    """Raw caller PCM retained until one VAD-delimited decode is due."""
    pcm: bytes
    retry_pcm: bytes
    start_ms: int
    end_ms: int
    reason: str


class CallerUtteranceBuffer:
    """Turn VAD frames into non-overlapping caller utterances.

    The caller path intentionally waits for an endpoint before Whisper.  A
    750 ms silence threshold is long enough to retain ordinary intra-sentence
    pauses while keeping a phone-call turn responsive.  Twelve seconds caps a
    hostile or unusually long monologue without returning to short windows.
    """
    def __init__(self, endpoint_silence_ms: int = 750, max_utterance_ms: int = 12_000,
                 pre_roll_ms: int = 250, retry_pre_roll_ms: int = 500,
                 post_roll_ms: int = 400, retry_post_roll_ms: int = 700):
        if endpoint_silence_ms <= 0 or max_utterance_ms <= endpoint_silence_ms:
            raise ValueError("invalid caller utterance timing")
        if not 200 <= pre_roll_ms <= 300 or not pre_roll_ms <= retry_pre_roll_ms:
            raise ValueError("invalid caller pre-roll timing")
        if not 300 <= post_roll_ms <= 500 or not post_roll_ms <= retry_post_roll_ms <= endpoint_silence_ms:
            raise ValueError("invalid caller post-roll timing")
        self.endpoint_silence_ms = endpoint_silence_ms
        self.max_utterance_ms = max_utterance_ms
        self.pre_roll_ms, self.retry_pre_roll_ms = pre_roll_ms, retry_pre_roll_ms
        self.post_roll_ms, self.retry_post_roll_ms = post_roll_ms, retry_post_roll_ms
        self._chunks: list[tuple[bytes, int, int]] = []
        self._pre_roll_chunks: deque[tuple[bytes, int, int]] = deque()
        self._utterance_pre_roll_chunks: tuple[tuple[bytes, int, int], ...] = ()
        self._start_ms: int | None = None
        self._last_voiced_end_ms: int | None = None

    @property
    def active(self) -> bool:
        return self._start_ms is not None

    def ingest(self, pcm: bytes, start_ms: int, end_ms: int, *, voiced: bool) -> list[FinalAudioUtterance]:
        if end_ms < start_ms:
            raise ValueError("audio end precedes start")
        if self._start_ms is None:
            if not voiced:
                self._remember_pre_roll(pcm, start_ms, end_ms)
                return []
            self._start_ms = start_ms
            self._utterance_pre_roll_chunks = tuple(self._pre_roll_chunks)
        self._chunks.append((pcm, start_ms, end_ms))
        if voiced:
            self._last_voiced_end_ms = end_ms
        elif self._last_voiced_end_ms is not None and end_ms - self._last_voiced_end_ms >= self.endpoint_silence_ms:
            result = [self._finalize("vad_silence")]
            self._remember_pre_roll(pcm, start_ms, end_ms)
            return result
        if end_ms - self._start_ms >= self.max_utterance_ms:
            result = [self._finalize("max_duration")]
            # A continuous hard-cap split must start the following utterance
            # cleanly, not seed it with the preceding utterance's speech.
            self._pre_roll_chunks.clear()
            return result
        self._remember_pre_roll(pcm, start_ms, end_ms)
        return []

    def finish(self, end_ms: int) -> list[FinalAudioUtterance]:
        if self._start_ms is None:
            return []
        return [self._finalize("end_of_stream")]

    @staticmethod
    def _pcm_range(chunks: Iterable[tuple[bytes, int, int]], start_ms: int, end_ms: int) -> bytes:
        parts: list[bytes] = []
        for pcm, chunk_start, chunk_end in chunks:
            overlap_start, overlap_end = max(start_ms, chunk_start), min(end_ms, chunk_end)
            if overlap_end <= overlap_start or chunk_end <= chunk_start:
                continue
            first = round((overlap_start - chunk_start) / (chunk_end - chunk_start) * len(pcm))
            last = round((overlap_end - chunk_start) / (chunk_end - chunk_start) * len(pcm))
            parts.append(pcm[first:last])
        return b"".join(parts)

    def _remember_pre_roll(self, pcm: bytes, start_ms: int, end_ms: int) -> None:
        self._pre_roll_chunks.append((pcm, start_ms, end_ms))
        minimum = end_ms - self.retry_pre_roll_ms
        while self._pre_roll_chunks and self._pre_roll_chunks[0][2] <= minimum:
            self._pre_roll_chunks.popleft()

    def _finalize(self, reason: str) -> FinalAudioUtterance:
        if self._start_ms is None or self._last_voiced_end_ms is None:
            raise RuntimeError("cannot finalize without voiced caller audio")
        pre_start = max(0, self._start_ms - self.pre_roll_ms)
        retry_pre_start = max(0, self._start_ms - self.retry_pre_roll_ms)
        audio_end = max(end for _, _, end in self._chunks)
        first_end = min(audio_end, self._last_voiced_end_ms + self.post_roll_ms)
        retry_end = min(audio_end, self._last_voiced_end_ms + self.retry_post_roll_ms)
        item = FinalAudioUtterance(
            self._pcm_range(self._utterance_pre_roll_chunks, pre_start, self._start_ms) + self._pcm_range(self._chunks, self._start_ms, first_end),
            self._pcm_range(self._utterance_pre_roll_chunks, retry_pre_start, self._start_ms) + self._pcm_range(self._chunks, self._start_ms, retry_end),
            pre_start, self._last_voiced_end_ms, reason,
        )
        self._chunks.clear()
        self._utterance_pre_roll_chunks = ()
        self._start_ms = self._last_voiced_end_ms = None
        return item

@dataclass
class Utterance:
    id: str
    speaker: str
    text: str
    start_ms: int
    end_ms: int
    stable: bool = True
    metadata: dict = field(default_factory=dict)

@dataclass
class CallRiskState:
    claimed_identity: str | None = None
    pretext: str | None = None
    requested_action: str | None = None
    requested_target: str | None = None
    credential_request: bool = False
    financial_action: bool = False
    remote_access_request: bool = False
    urgency: bool = False
    secrecy_pressure: bool = False
    fear_pressure: bool = False
    protective_advice: bool = False
    negation: bool = False
    quotation_or_hypothetical: bool = False
    risk_level: str = "SAFE"
    risk_reasons: list[str] = field(default_factory=list)
    last_updated_at: float = 0.0

class PriorityASRScheduler:
    """One model consumer; caller queue always wins over user work."""
    def __init__(self, max_items: int = 24):
        self.caller: queue.Queue[AudioWork] = queue.Queue(max_items)
        self.user: queue.Queue[AudioWork] = queue.Queue(max_items)
        self.dropped_user = 0
        self.dropped_caller = 0
    def submit(self, work: AudioWork) -> bool:
        target = self.caller if work.speaker == CALLER else self.user
        try: target.put_nowait(work); return True
        except queue.Full:
            if work.speaker == USER: self.dropped_user += 1; return False
            # Keep bounded latency: a newer caller window replaces the oldest
            # caller window rather than allowing an ever-growing delay.
            try: self.caller.get_nowait(); self.dropped_caller += 1
            except queue.Empty: return False
            self.caller.put_nowait(work); return True
    def next(self) -> AudioWork | None:
        try: return self.caller.get_nowait()
        except queue.Empty:
            try: return self.user.get_nowait()
            except queue.Empty: return None

def overlap_deduplicate(stable: str, incoming: str) -> str:
    """Append only the non-overlapping word suffix; robust to incremental Whisper windows."""
    a, b = stable.split(), incoming.split()
    max_overlap = min(len(a), len(b))
    for size in range(max_overlap, 0, -1):
        if [w.lower() for w in a[-size:]] == [w.lower() for w in b[:size]]:
            return " ".join(a + b[size:])
    return " ".join(a + b)

class TranscriptStabilizer:
    def __init__(self):
        self.stable = ""
        self.partial = ""
        self._last = ""
        self._emitted = ""
    def update(self, text: str, utterance_closed: bool = False) -> tuple[str, str, str]:
        self.partial = text.strip()
        if not self.partial: return self.partial, self.stable, ""
        # Confirmation by an overlapping later window, or explicit VAD close.
        if utterance_closed or self._last:
            self.stable = overlap_deduplicate(self.stable, self.partial)
        self._last = self.partial
        # Only hand the assembler the new stable suffix.  Re-emitting the whole
        # aggregate would turn overlapping ASR windows into duplicate dialogue.
        before = self._emitted.split()
        after = self.stable.split()
        if len(after) >= len(before) and [x.lower() for x in after[:len(before)]] == [x.lower() for x in before]:
            delta = " ".join(after[len(before):])
        else:
            delta = self.stable
        if delta:
            self._emitted = self.stable
        return self.partial, self.stable, delta


@dataclass
class StreamingStabilizerEvent:
    """One timestamp-aware update to a caller's in-progress utterance."""
    action: str
    provisional_text: str | None
    committed_text: str | None
    audio_start_ms: int | None
    audio_end_ms: int | None
    finalization_reason: str | None
    reason: str | None = None
    analysis_text_changed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _normalised_words(text: str) -> list[str]:
    return re.findall(r"[\w'-]+", text.lower(), re.UNICODE)


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None


class StreamingTranscriptStabilizer:
    """Keep one provisional utterance until an audio boundary finalizes it.

    Whisper windows overlap by design.  A later window therefore updates the
    active utterance rather than being a second conversation turn.  This class
    deliberately has no call-level language state: each candidate is assessed
    only against its active provisional utterance and its audio coverage.
    """
    def __init__(self):
        self._provisional: dict[str, Any] | None = None
        self._committed: list[dict[str, Any]] = []

    @property
    def committed_texts(self) -> list[str]:
        return [str(turn["text"]) for turn in self._committed]

    @property
    def committed_transcript(self) -> str:
        return " ".join(self.committed_texts)

    @property
    def provisional_text(self) -> str | None:
        return None if self._provisional is None else str(self._provisional["text"])

    def nomic_turns(self, speaker: str = CALLER) -> list[tuple[str, str]]:
        turns = [(speaker, text) for text in self.committed_texts]
        if self._provisional and self._provisional["text"]:
            turns.append((speaker, str(self._provisional["text"])))
        return turns

    @staticmethod
    def _overlap_ratio(previous: Mapping[str, Any], incoming: Mapping[str, Any]) -> tuple[int, float, int]:
        overlap = max(0, min(int(previous["end_ms"]), int(incoming["end_ms"])) - max(int(previous["start_ms"]), int(incoming["start_ms"])))
        duration = max(1, min(int(previous["end_ms"]) - int(previous["start_ms"]), int(incoming["end_ms"]) - int(incoming["start_ms"])))
        new_audio = max(0, int(incoming["end_ms"]) - max(int(incoming["start_ms"]), int(previous["end_ms"])))
        return overlap, overlap / duration, new_audio

    @staticmethod
    def _lexical_agreement(left: str, right: str) -> float:
        a, b = set(_normalised_words(left)), set(_normalised_words(right))
        return len(a & b) / max(1, len(a | b))

    @staticmethod
    def _merge(previous: str, incoming: str) -> str:
        old, new = previous.split(), incoming.split()
        old_keys, new_keys = _normalised_words(previous), _normalised_words(incoming)
        # Whisper commonly completes the final token of an earlier partial
        # (``cod`` -> ``code``); that is a revision, not a new suffix.
        if previous.lower().startswith(incoming.lower()):
            return previous
        if incoming.lower().startswith(previous.lower()):
            return incoming
        if old_keys and new_keys and old_keys == new_keys[:len(old_keys)]:
            return incoming
        if old_keys and new_keys and new_keys == old_keys[:len(new_keys)]:
            return previous
        # A later overlapping decode often contains only the tail of the
        # current utterance.  It must neither replace the confirmed prefix nor
        # be appended as a duplicate sentence.  Punctuation is ignored solely
        # for alignment; the retained text remains original Whisper output.
        for size in range(min(len(old_keys), len(new_keys)), 0, -1):
            if old_keys[-size:] == new_keys[:size]:
                return " ".join(old + new[size:])
        return " ".join(old + new)

    def _weak_overlapping_disagreement(self, previous: Mapping[str, Any], incoming: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
        overlap_ms, overlap_ratio, new_audio_ms = self._overlap_ratio(previous, incoming)
        agreement = self._lexical_agreement(str(previous["text"]), str(incoming["text"]))
        language_probability = _as_float(incoming.get("languageProbability"))
        average_logprob = _as_float(incoming.get("averageLogProb"))
        no_speech_probability = _as_float(incoming.get("noSpeechProbability"))
        weak = (
            overlap_ratio >= 0.50 and new_audio_ms <= 1000 and agreement < 0.20
            and language_probability is not None and language_probability <= 0.55
            and average_logprob is not None and average_logprob <= -0.80
            and no_speech_probability is not None and no_speech_probability >= 0.30
        )
        return weak, {"overlap_ms": overlap_ms, "overlap_ratio": round(overlap_ratio, 4), "new_audio_ms": new_audio_ms,
                      "lexical_agreement": round(agreement, 4), "language_probability": language_probability,
                      "average_logprob": average_logprob, "no_speech_probability": no_speech_probability}

    def _commit(self, reason: str) -> str | None:
        if self._provisional is None or not self._provisional["text"]:
            return None
        turn = {**self._provisional, "finalization_reason": reason}
        self._committed.append(turn)
        self._provisional = None
        return str(turn["text"])

    def process(self, hypothesis: Mapping[str, Any], *, end_of_stream: bool = False, speech_boundary: bool = False) -> StreamingStabilizerEvent:
        """Apply one Whisper window. ``speech_boundary`` is a VAD endpoint."""
        text = " ".join(str(hypothesis.get("text", "")).split())
        start_ms, end_ms = int(hypothesis["start_ms"]), int(hypothesis["end_ms"])
        candidate = dict(hypothesis)
        candidate.update({"text": text, "start_ms": start_ms, "end_ms": end_ms})
        action, reason, changed = "IGNORED_EMPTY", "empty_hypothesis", False
        committed_text: str | None = None
        if text:
            if self._provisional is None:
                self._provisional = candidate
                action, reason, changed = "PROVISIONAL", "first_hypothesis", True
            elif start_ms < int(self._provisional["end_ms"]):
                weak, evidence = self._weak_overlapping_disagreement(self._provisional, candidate)
                if weak:
                    action, reason = "IGNORED_OVERLAP", "weak_overlapping_disagreement"
                else:
                    merged = self._merge(str(self._provisional["text"]), text)
                    changed = merged != self._provisional["text"]
                    self._provisional.update(candidate)
                    self._provisional["text"] = merged
                    self._provisional["start_ms"] = min(int(self._provisional["start_ms"]), start_ms)
                    self._provisional["end_ms"] = max(int(self._provisional["end_ms"]), end_ms)
                    action, reason = "REVISED", "overlapping_hypothesis"
                candidate["overlap_evidence"] = evidence
            else:
                committed_text = self._commit("next_non_overlapping_speech")
                self._provisional = candidate
                action, reason, changed = "NEW_PROVISIONAL", "non_overlapping_speech", True
        if speech_boundary or end_of_stream:
            final_reason = "vad_speech_boundary" if speech_boundary else "end_of_stream"
            finalized = self._commit(final_reason)
            committed_text = finalized or committed_text
            if action in {"PROVISIONAL", "REVISED", "IGNORED_EMPTY"} and finalized:
                action = "COMMITTED"
                reason = final_reason
            # An ignored tail can still close the valid earlier provisional.
            finalization_reason = final_reason if finalized else None
        else:
            finalization_reason = None
        return StreamingStabilizerEvent(action, self.provisional_text, committed_text, start_ms, end_ms,
                                        finalization_reason, reason, changed, candidate)

class ConversationAssembler:
    def __init__(self): self.turns: list[Utterance] = []
    def emit(self, speaker: str, text: str, start_ms: int, end_ms: int, metadata: dict | None = None) -> Utterance | None:
        text = " ".join(text.split())
        if not text: return None
        turn = Utterance(str(uuid.uuid4()), speaker, text, start_ms, end_ms, True, metadata or {})
        self.turns.append(turn); self.turns.sort(key=lambda item: (item.start_ms, item.end_ms, item.id)); return turn
    def suppress_mic_leak(self, user: Utterance, threshold_ms: int = 2500) -> bool:
        words = set(re.findall(r"\w+", user.text.lower()))
        if not words: return False
        for caller in self.turns:
            if caller.speaker != CALLER or abs(caller.end_ms - user.end_ms) > threshold_ms: continue
            other = set(re.findall(r"\w+", caller.text.lower()))
            if len(words & other) / max(1, len(words)) >= .75:
                user.metadata["probableMicLeak"] = True; return True
        return False

class AnalysisScheduler:
    """One asynchronous analysis slot; while occupied, retain only latest coalesced update."""
    def __init__(self): self.in_flight = False; self.pending: list[Utterance] = []
    def offer(self, turns: Iterable[Utterance]) -> bool:
        self.pending.extend(turns)
        if self.in_flight: return False
        self.in_flight = True; return True
    def complete(self) -> list[Utterance]:
        result, self.pending = self.pending, []; self.in_flight = False; return result
    def payload(self, state: CallRiskState, turns: list[Utterance], metadata: dict) -> dict:
        return {"previousState": asdict(state), "newUtterances": [asdict(t) for t in turns], "recentDialogue": [asdict(t) for t in turns[-8:]], "callMetadata": metadata}

class DualChannelPipeline:
    def __init__(self, transcribe: Callable[[bytes], str]):
        self.transcribe, self.scheduler = transcribe, PriorityASRScheduler()
        self.stabilizers = {CALLER: TranscriptStabilizer(), USER: TranscriptStabilizer()}
        self.streaming_stabilizers = {CALLER: StreamingTranscriptStabilizer(), USER: StreamingTranscriptStabilizer()}
        self.assembler, self.risk, self.analysis = ConversationAssembler(), CallRiskState(), AnalysisScheduler()
        self.metrics: list[dict] = []
    @staticmethod
    def has_speech(pcm: bytes, threshold: int = 180) -> bool:
        """Cheap frame-level VAD gate; Whisper remains the speech authority."""
        if len(pcm) < 4:
            return False
        # Stereo PCM16 capture is accepted by the caller path.  audioop rms is
        # intentionally conservative so a silent mic never consumes ASR slots.
        return audioop.rms(pcm, 2) >= threshold

    def ingest(self, speaker: str, pcm: bytes, start_ms: int, end_ms: int) -> bool:
        now = time.monotonic()
        # Tiny in-memory payloads are used by deterministic unit tests; real
        # 48 kHz capture chunks are always much larger and are VAD-gated.
        if len(pcm) >= 320 and not self.has_speech(pcm):
            return False
        return self.scheduler.submit(AudioWork(speaker, pcm, start_ms, end_ms, Timing(now, now)))
    def drain_once(self, utterance_closed: bool = True) -> Utterance | None:
        work = self.scheduler.next()
        if not work: return None
        work.timing.asr_started_at = time.monotonic(); text = self.transcribe(work.pcm); work.timing.partial_ready_at = time.monotonic()
        partial, stable, delta = self.stabilizers[work.speaker].update(text, utterance_closed); work.timing.stable_text_ready_at = time.monotonic()
        turn = self.assembler.emit(work.speaker, delta if utterance_closed else partial, work.start_ms, work.end_ms, {"partial": partial, "stableAggregate": stable})
        if turn:
            work.timing.utterance_finalized_at = time.monotonic()
            if turn.speaker == USER and self.assembler.suppress_mic_leak(turn): return None
            self.metrics.append({"speaker": work.speaker, "asrMs": round((work.timing.partial_ready_at-work.timing.asr_started_at)*1000,1), "speechToPartialMs": round((work.timing.partial_ready_at-work.timing.speech_detected_at)*1000,1), "speechToStableMs": round((work.timing.stable_text_ready_at-work.timing.speech_detected_at)*1000,1)})
        return turn

    def drain_streaming_once(self, *, speech_boundary: bool = False, end_of_stream: bool = False) -> StreamingStabilizerEvent | None:
        """Decode one window without turning an overlap revision into a turn.

        The legacy ``drain_once`` remains for existing capture consumers.  New
        replay/live callers use this method so Nomic can see committed history
        plus the one current provisional caller utterance.
        """
        work = self.scheduler.next()
        if not work:
            return None
        work.timing.asr_started_at = time.monotonic()
        decoded = self.transcribe(work.pcm)
        work.timing.partial_ready_at = time.monotonic()
        if isinstance(decoded, Mapping):
            hypothesis = dict(decoded)
            text = str(hypothesis.get("text", ""))
        else:
            text, hypothesis = str(decoded), {}
        hypothesis.update({"text": text, "start_ms": work.start_ms, "end_ms": work.end_ms})
        event = self.streaming_stabilizers[work.speaker].process(hypothesis, speech_boundary=speech_boundary, end_of_stream=end_of_stream)
        work.timing.stable_text_ready_at = time.monotonic()
        if event.committed_text:
            turn = self.assembler.emit(work.speaker, event.committed_text, work.start_ms, work.end_ms, {
                "provisional_text": event.provisional_text, "finalization_reason": event.finalization_reason,
                "stabilizer_action": event.action, "stabilizer_reason": event.reason,
            })
            if turn:
                work.timing.utterance_finalized_at = time.monotonic()
        self.metrics.append({"speaker": work.speaker, "asrMs": round((work.timing.partial_ready_at-work.timing.asr_started_at)*1000,1),
                             "speechToPartialMs": round((work.timing.partial_ready_at-work.timing.speech_detected_at)*1000,1),
                             "speechToStableMs": round((work.timing.stable_text_ready_at-work.timing.speech_detected_at)*1000,1),
                             "stabilizerAction": event.action, "finalizationReason": event.finalization_reason})
        return event
