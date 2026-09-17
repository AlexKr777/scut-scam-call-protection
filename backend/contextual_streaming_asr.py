"""Evidence-preserving, latest-only caller ASR orchestration.

Rolling revisions are useful for responsiveness, but they are never treated as
the sole truth for a completed utterance. A VAD endpoint produces an
independent full-buffer decode and the arbiter retains every candidate.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import re, time
from typing import Callable, Any
from .dual_pass_asr import ASRText
from .realtime_pipeline import DualChannelPipeline

SAMPLE_BYTES_PER_MS = 48_000 * 2 * 2 // 1000
# Escapes keep these semantic tokens stable even when a Windows editor opens a
# requirements or source file with a legacy code page.
NEGATION = {"ru": {"\u043d\u0435", "\u043d\u0438\u043a\u043e\u043c\u0443", "\u043d\u0438\u043a\u043e\u0433\u0434\u0430", "\u043d\u0435\u043b\u044c\u0437\u044f"}, "en": {"not", "never", "don't", "do", "nobody"}, "ro": {"nu", "nim\u0103nui", "niciodat\u0103"}}
def words(text: str) -> list[str]: return re.findall(r"[\w'-]+", text.lower(), re.UNICODE)
def _negations(text: str) -> set[str]:
    value=set(words(text)); return set().union(*(value & terms for terms in NEGATION.values()))

@dataclass
class TranscriptCandidate:
    text: str
    source_kind: str
    language: str = "und"
    language_probability: float = 0.0
    avg_logprob: float | None = None
    no_speech_probability: float | None = None
    compression_ratio: float | None = None
    segment_timestamps: list[dict] = field(default_factory=list)
    audio_coverage: float = 0.0
    decode_duration_ms: float = 0.0
    generated_at: float = field(default_factory=time.time)
    agreement_with_previous: float = 0.0
    quality_flags: list[str] = field(default_factory=list)
    uncertainty_flags: list[str] = field(default_factory=list)
    normalized_tokens: list[str] = field(default_factory=list)
    supporting_revision_count: int = 0
    independent_support_count: int = 0
    agreement_with_rolling: float = 0.0
    agreement_with_endpoint: float = 0.0
    agreement_with_confirmation: float = 0.0
    polarity_conflict: bool = False
    selected: bool = False
    decision_reason: str | None = None
    def diagnostic(self) -> dict[str, Any]: return asdict(self)

@dataclass
class LanguageLock:
    preferred: str | None = None; language: str | None = None; confidence: float = 0.0
    evidence: list[tuple[str, float]] = field(default_factory=list); locked: bool = False
    def __post_init__(self):
        if self.preferred in {"ru", "ro", "en"}: self.language, self.confidence, self.locked = self.preferred, 1.0, True
    def observe(self, language: str, probability: float, informative: bool = True) -> str | None:
        if language not in {"ru", "ro", "en"} or not informative: return self.language
        self.evidence.append((language, probability)); self.evidence=self.evidence[-6:]
        scores={key:sum(p for lang,p in self.evidence if lang==key) for key in ("ru","ro","en")}; candidate=max(scores,key=scores.get); total=sum(scores.values()) or 1
        threshold=.72 if candidate==self.preferred else 1.35
        if not self.locked and scores[candidate]>=threshold and scores[candidate]/total>=.62: self.language,self.confidence,self.locked=candidate,scores[candidate]/total,True
        # A confident lock is sticky: a foreign result is quality evidence, not a silent switch.
        return self.language
CallLanguageController = LanguageLock

class LocalAgreement:
    def __init__(self): self.previous=[]; self.confirmed=[]; self.timeline=[]
    def update(self,text:str,at_ms:int,final:bool=False)->dict:
        current=words(text); common=0
        while common<min(len(self.previous),len(current)) and self.previous[common]==current[common]: common+=1
        if self.previous and common>len(self.confirmed): self.confirmed=self.previous[:common]
        self.previous=current
        row={"atMs":at_ms,"fastPartial":text,"confirmedPrefix":" ".join(self.confirmed),"stable":final,"negationUnstable":bool(_negations(text)) and not final and len(self.confirmed)<len(current)}
        self.timeline.append(row); return row

@dataclass
class PendingDecode: pcm: bytes; start_ms: int; end_ms: int
class LatestOnlyCallerScheduler:
    def __init__(self): self.pending=None; self.running=False; self.coalesced=0; self.max_pending=0
    def offer(self,item):
        if self.pending is not None:self.coalesced+=1
        self.pending=item;self.max_pending=max(self.max_pending,1)
    def take(self):
        if self.running or not self.pending:return None
        item,self.pending,self.running=self.pending,None,True;return item
    def done(self):self.running=False

def _agreement(a,b):
    left,right=set(words(a)),set(words(b)); return len(left&right)/max(1,len(left|right))
def _divergent(a,b):
    """Meaningful lexical disagreement, ignoring punctuation and small edits."""
    return bool(words(a) and words(b)) and _agreement(a,b) < .42
def _quality(c,locked,voiced):
    flags=[]
    if not c.text.strip() and voiced:flags.append("EMPTY_AFTER_VOICED_AUDIO")
    if c.no_speech_probability is not None and c.no_speech_probability>.80:flags.append("HIGH_NO_SPEECH")
    if c.avg_logprob is not None and c.avg_logprob<-1.25:flags.append("POOR_LOGPROB")
    if c.compression_ratio is not None and c.compression_ratio>2.8:flags.append("PATHOLOGICAL_COMPRESSION")
    tokens=words(c.text)
    if len(tokens)>=4 and len(set(tokens))<=max(1,len(tokens)//3):flags.append("REPETITIVE_NGRAM")
    if locked and c.language not in {locked,"und",""}:flags.append("LOCKED_LANGUAGE_MISMATCH")
    return flags
class CandidateArbiter:
    BAD={"EMPTY_AFTER_VOICED_AUDIO","HIGH_NO_SPEECH","POOR_LOGPROB","PATHOLOGICAL_COMPRESSION","REPETITIVE_NGRAM","LOCKED_LANGUAGE_MISMATCH"}
    def _quality_strength(self,c):
        if not c.text.strip() or any(f in self.BAD for f in c.quality_flags): return -10
        score=1.0
        if c.language_probability >= .80: score += .75
        elif c.language_probability and c.language_probability < .50: score -= .75
        if c.avg_logprob is not None:
            score += 1 if c.avg_logprob >= -.75 else .35 if c.avg_logprob >= -1.25 else -1
        if c.no_speech_probability is not None and c.no_speech_probability > .70: score -= .75
        if c.compression_ratio is not None and c.compression_ratio > 2.4: score -= .75
        return score

    def _annotate(self,candidates):
        meaningful=[c for c in candidates if c.text.strip() and not any(f in self.BAD for f in c.quality_flags)]
        for c in candidates:
            c.normalized_tokens=words(c.text)
            c.agreement_with_rolling=max((_agreement(c.text,o.text) for o in candidates if o.source_kind in {"ROLLING_PARTIAL","CONFIRMED_PREFIX"} and o is not c),default=0.)
            c.agreement_with_endpoint=max((_agreement(c.text,o.text) for o in candidates if o.source_kind=="ENDPOINT_WHOLE" and o is not c),default=0.)
            c.agreement_with_confirmation=max((_agreement(c.text,o.text) for o in candidates if o.source_kind=="CONFLICT_REDECODE" and o is not c),default=0.)
            family=[o for o in meaningful if o is not c and _agreement(c.text,o.text)>=.58]
            c.supporting_revision_count=sum(o.source_kind=="ROLLING_PARTIAL" for o in family)
            c.independent_support_count=len({o.source_kind for o in family if o.source_kind != "CONFIRMED_PREFIX"})
            c.polarity_conflict=any(bool(_negations(c.text)|_negations(o.text)) and _negations(c.text)!=_negations(o.text) for o in meaningful if o is not c)
        return meaningful

    def score(self,c):
        # No source-kind bonus: repeated compatible evidence and decoder facts
        # are the only route to a materially stronger candidate.
        return self._quality_strength(c)+1.20*c.supporting_revision_count+.60*max(0,c.independent_support_count-1)+.15*min(len(c.normalized_tokens),12)

    def decide(self,candidates):
        meaningful=self._annotate(candidates)
        if not meaningful:
            return None,"UNKNOWN_TRANSCRIPT","unknown_all_candidates_unreliable",False
        ranked=sorted(meaningful,key=self.score,reverse=True); best=ranked[0]
        runner=ranked[1] if len(ranked)>1 else None
        materially_divergent=runner is not None and _divergent(best.text,runner.text)
        close=runner is not None and self.score(best)-self.score(runner)<.85
        polarity=any(c.polarity_conflict for c in meaningful)
        confirmation=[c for c in meaningful if c.source_kind=="CONFLICT_REDECODE"]
        # A confirmation participates by joining the lexical family; if three
        # plausible families remain, uncertainty is safer than recency.
        if confirmation and materially_divergent and close and all(_divergent(confirmation[0].text,c.text) for c in meaningful if c is not confirmation[0]):
            return None,"UNCERTAIN_CONFLICT","uncertain_material_conflict",True
        if (polarity or materially_divergent) and runner is not None and close and not confirmation:
            return best,"UNCERTAIN_CONFLICT","uncertain_material_conflict",True
        if best.source_kind=="ENDPOINT_WHOLE":
            reason="endpoint_and_confirmation_agree" if best.agreement_with_confirmation>=.58 else "endpoint_won_stronger_full_context_evidence"
        elif best.source_kind=="CONFLICT_REDECODE":
            reason="rolling_and_confirmation_agree" if best.agreement_with_rolling>=.58 else "confirmation_won_stronger_evidence"
        elif best.supporting_revision_count>=2:
            reason="rolling_won_multi_revision_consensus"
        elif best.agreement_with_confirmation>=.58:
            reason="rolling_and_confirmation_agree"
        else:
            reason="rolling_preserved_endpoint_lower_agreement"
        return best,"CONFIDENT_TRANSCRIPT",reason,bool(polarity or materially_divergent)
    def choose(self,candidates):
        selected,_,_,conflict=self.decide(candidates); return selected,conflict

class ContextualStreamingCallerASR:
    def __init__(self,fast:Callable[[bytes,str|None],ASRText],preferred_language:str|None=None,max_context_ms:int=6000,cadence_ms:int=1000,end_pause_ms:int=500,confirmation:Callable[[bytes,str|None],ASRText]|None=None):
        self.fast,self.confirmation,self.language=fast,confirmation or fast,LanguageLock(preferred_language);self.max_context_ms,self.cadence_ms,self.end_pause_ms=max_context_ms,cadence_ms,end_pause_ms
        self.buffer=bytearray();self.utterance_start_ms=None;self.last_decode_ms=-cadence_ms;self.last_speech_ms=None;self.scheduler,self.agreement,self.arbiter=LatestOnlyCallerScheduler(),LocalAgreement(),CandidateArbiter()
        self.metrics=[];self.candidates=[];self.stable_fast="";self.fast_partial=""
    def ingest_caller(self,pcm,start_ms,end_ms):
        if DualChannelPipeline.has_speech(pcm):
            if self.utterance_start_ms is None:self.utterance_start_ms=start_ms
            self.buffer.extend(pcm);self.last_speech_ms=end_ms
            if end_ms-self.last_decode_ms>=self.cadence_ms:self._offer_context(end_ms)
        elif self.last_speech_ms is not None and end_ms-self.last_speech_ms>=self.end_pause_ms:self.confirm_end_of_utterance(end_ms)
    def _context(self):return bytes(self.buffer[-self.max_context_ms*SAMPLE_BYTES_PER_MS:])
    def _offer_context(self,end_ms):
        if self.utterance_start_ms is not None:self.scheduler.offer(PendingDecode(self._context(),max(self.utterance_start_ms,end_ms-self.max_context_ms),end_ms));self.last_decode_ms=end_ms
    def _candidate(self,result,source,started,coverage,prior=""):
        extra=getattr(result,"evidence",{}) or {}; c=TranscriptCandidate(result.text.strip(),source,result.language,result.language_probability,extra.get("avg_logprob"),extra.get("no_speech_probability"),extra.get("compression_ratio"),extra.get("segments",[]),coverage,round((time.perf_counter()-started)*1000,1),agreement_with_previous=_agreement(result.text,prior))
        c.quality_flags=_quality(c,self.language.language if self.language.locked else None,bool(self.buffer));return c
    def drain_fast_once(self):
        job=self.scheduler.take()
        if not job:return None
        started=time.perf_counter()
        try:
            passed=self.language.language if self.language.locked else None; result=self.fast(job.pcm,passed);self.language.observe(result.language,result.language_probability,bool(result.text));c=self._candidate(result,"ROLLING_PARTIAL",started,1.,self.fast_partial);self.candidates.append(c);self.fast_partial=c.text
            row=self.agreement.update(c.text,job.end_ms);row.update({"kind":"FAST_PARTIAL","languageArgument":passed,"language":result.language,"languageProbability":result.language_probability,"decodeMs":c.decode_duration_ms,"contextMs":round(len(job.pcm)/SAMPLE_BYTES_PER_MS),"coalesced":self.scheduler.coalesced,"candidate":c.diagnostic()});self.metrics.append(row);return row
        finally:self.scheduler.done()
    def confirm_end_of_utterance(self,at_ms):
        if not self.buffer or self.utterance_start_ms is None:return None
        full,duration=bytes(self.buffer),len(self.buffer)/SAMPLE_BYTES_PER_MS;passed=self.language.language if self.language.locked else None
        started=time.perf_counter();raw=self.fast(full,passed);self.language.observe(raw.language,raw.language_probability,bool(raw.text));endpoint=self._candidate(raw,"ENDPOINT_WHOLE",started,1.,self.fast_partial);self.candidates.append(endpoint)
        prefix=" ".join(self.agreement.confirmed)
        if prefix:
            confirmed=TranscriptCandidate(prefix,"CONFIRMED_PREFIX",self.language.language or "und",agreement_with_previous=_agreement(prefix,self.fast_partial));confirmed.quality_flags=_quality(confirmed,self.language.language if self.language.locked else None,True);self.candidates.append(confirmed)
        selected,status,reason,conflict=self.arbiter.decide(self.candidates)
        if conflict:
            started=time.perf_counter();redo=self.confirmation(full,passed);confirmation=self._candidate(redo,"CONFLICT_REDECODE",started,1.,endpoint.text);self.candidates.append(confirmation);selected,status,reason,_=self.arbiter.decide(self.candidates)
        for candidate in self.candidates:
            candidate.selected=candidate is selected and status=="CONFIDENT_TRANSCRIPT"
            candidate.decision_reason=reason if candidate.selected else None
        self.stable_fast=selected.text if selected and status=="CONFIDENT_TRANSCRIPT" else "";row=self.agreement.update(self.stable_fast,at_ms,final=True)
        row.update({"kind":"FINAL","status":status,"selectionReason":reason,"languageArgument":passed,"rollingBestTranscript":self.fast_partial,"rollingConfirmedPrefix":prefix,"rollingLastTranscript":self.fast_partial,"wholeUtteranceTranscript":endpoint.text,"finalTranscript":self.stable_fast,"audioDurationMs":round(duration),"endOfSpeechToFinalReadyMs":endpoint.decode_duration_ms,"candidates":[c.diagnostic() for c in self.candidates],"selectedSource":selected.source_kind if selected and status=="CONFIDENT_TRANSCRIPT" else None})
        self.metrics.append(row);self.buffer.clear();self.utterance_start_ms=self.last_speech_ms=None;return row
