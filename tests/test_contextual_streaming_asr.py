import struct
import unittest
from backend.contextual_streaming_asr import LanguageLock, LocalAgreement, LatestOnlyCallerScheduler, PendingDecode, ContextualStreamingCallerASR, TranscriptCandidate, CandidateArbiter
from backend.dual_pass_asr import ASRText


class ContextualStreamingTests(unittest.TestCase):
    def test_language_lock_is_sticky_and_needs_sustained_switch_evidence(self):
        lock=LanguageLock(); lock.observe("ru", .9); lock.observe("ru", .9)
        self.assertEqual("ru", lock.language); lock.observe("en", .99)
        self.assertEqual("ru", lock.language)

    def test_configured_language_is_locked_before_first_short_partial(self):
        self.assertEqual("ru", LanguageLock("ru").language)

    def test_latest_only_replaces_obsolete_partial(self):
        s=LatestOnlyCallerScheduler(); s.offer(PendingDecode(b"old",0,1)); s.offer(PendingDecode(b"new",1,2))
        self.assertEqual(b"new",s.take().pcm); self.assertEqual(1,s.coalesced); s.done()

    def test_local_agreement_does_not_commit_wrong_earlier_partial(self):
        a=LocalAgreement(); a.update("давайте код из смс",1000); row=a.update("никому не называйте код из смс",2000)
        self.assertEqual("",row["confirmedPrefix"])
        final=a.update("никому не называйте код из смс",2500,final=True)
        self.assertEqual("никому не называйте код из смс",final["confirmedPrefix"])

    def test_vad_pause_produces_stable_fast(self):
        pcm=struct.pack("<"+"h"*(48_000*2),*([1000,1000]*48_000))
        seen=[]
        engine=ContextualStreamingCallerASR(lambda raw,lang: ASRText("никому не называйте код из SMS",lang or "ru",.99),preferred_language="ru",cadence_ms=500,end_pause_ms=500)
        engine.ingest_caller(pcm,0,1000); seen.append(engine.drain_fast_once())
        engine.ingest_caller(b"\0"*(48_000*2),1000,1500)
        self.assertEqual("никому не называйте код из SMS",engine.stable_fast)
        self.assertEqual("FINAL",engine.metrics[-1]["kind"])

    def test_empty_endpoint_cannot_erase_confirmed_evidence(self):
        arbiter=CandidateArbiter()
        earlier=TranscriptCandidate("не сообщайте код никому", "CONFIRMED_PREFIX", "ru")
        empty=TranscriptCandidate("", "ENDPOINT_WHOLE", "ru")
        empty.quality_flags=["EMPTY_AFTER_VOICED_AUDIO"]
        selected, conflict=arbiter.choose([earlier, empty])
        self.assertEqual(earlier, selected); self.assertFalse(conflict)

    def test_wrong_language_endpoint_cannot_erase_locked_transcript(self):
        arbiter=CandidateArbiter(); russian=TranscriptCandidate("не сообщайте код", "CONFIRMED_PREFIX", "ru")
        english=TranscriptCandidate("thank you", "ENDPOINT_WHOLE", "en"); english.quality_flags=["LOCKED_LANGUAGE_MISMATCH"]
        self.assertEqual(russian, arbiter.choose([russian,english])[0])

    def test_polarity_conflict_is_not_silently_final(self):
        arbiter=CandidateArbiter(); a=TranscriptCandidate("share the code", "ROLLING_PARTIAL", "en")
        b=TranscriptCandidate("do not share the code", "ENDPOINT_WHOLE", "en", audio_coverage=1)
        self.assertTrue(arbiter.choose([a,b])[1])

    def test_rolling_consensus_survives_one_divergent_endpoint(self):
        arbiter=CandidateArbiter()
        rolling=[TranscriptCandidate("please share the account code", "ROLLING_PARTIAL", "en", language_probability=.99) for _ in range(3)]
        endpoint=TranscriptCandidate("subtitle editor credits", "ENDPOINT_WHOLE", "en", language_probability=.99, audio_coverage=1)
        selected,status,reason,_=arbiter.decide(rolling+[endpoint])
        self.assertEqual(rolling[0].text, selected.text); self.assertEqual("CONFIDENT_TRANSCRIPT",status)
        self.assertEqual("rolling_won_multi_revision_consensus",reason)

    def test_stronger_full_context_can_correct_weak_partial(self):
        arbiter=CandidateArbiter()
        rolling=TranscriptCandidate("share code", "ROLLING_PARTIAL", "en", avg_logprob=-1.6, language_probability=.4)
        endpoint=TranscriptCandidate("do not share the account code with anyone", "ENDPOINT_WHOLE", "en", avg_logprob=-.2, language_probability=.99, audio_coverage=1)
        selected,status,reason,_=arbiter.decide([rolling,endpoint])
        self.assertEqual(endpoint,selected); self.assertEqual("CONFIDENT_TRANSCRIPT",status)
        self.assertEqual("endpoint_won_stronger_full_context_evidence",reason)

    def test_confirmation_supports_rolling_polarity_family(self):
        arbiter=CandidateArbiter()
        rolling=TranscriptCandidate("do not share the code", "ROLLING_PARTIAL", "en", language_probability=.99)
        endpoint=TranscriptCandidate("share the code", "ENDPOINT_WHOLE", "en", language_probability=.99, audio_coverage=1)
        confirmation=TranscriptCandidate("do not share code", "CONFLICT_REDECODE", "en", language_probability=.99)
        selected,status,reason,_=arbiter.decide([rolling,endpoint,confirmation])
        self.assertIn(selected.text,{rolling.text,confirmation.text}); self.assertEqual("rolling_and_confirmation_agree",reason)

    def test_confirmation_supports_endpoint_polarity_family(self):
        arbiter=CandidateArbiter()
        rolling=TranscriptCandidate("do not share code", "ROLLING_PARTIAL", "en", language_probability=.3, avg_logprob=-1.5)
        endpoint=TranscriptCandidate("share the account code", "ENDPOINT_WHOLE", "en", language_probability=.99, avg_logprob=-.2, audio_coverage=1)
        confirmation=TranscriptCandidate("share the account code", "CONFLICT_REDECODE", "en", language_probability=.99, avg_logprob=-.2)
        selected,status,reason,_=arbiter.decide([rolling,endpoint,confirmation])
        self.assertEqual(endpoint.text,selected.text); self.assertEqual("endpoint_and_confirmation_agree",reason)

    def test_unresolved_and_unknown_are_explicit(self):
        arbiter=CandidateArbiter()
        a=TranscriptCandidate("alpha bravo charlie", "ROLLING_PARTIAL", "en", language_probability=.9)
        b=TranscriptCandidate("delta echo foxtrot", "ENDPOINT_WHOLE", "en", language_probability=.9, audio_coverage=1)
        c=TranscriptCandidate("golf hotel india", "CONFLICT_REDECODE", "en", language_probability=.9)
        self.assertEqual("UNCERTAIN_CONFLICT",arbiter.decide([a,b,c])[1])
        empty=TranscriptCandidate("", "ENDPOINT_WHOLE", "en"); empty.quality_flags=["EMPTY_AFTER_VOICED_AUDIO"]
        self.assertEqual("UNKNOWN_TRANSCRIPT",arbiter.decide([empty])[1])
