import unittest
from backend.realtime_pipeline import *

class RealtimePipelineTests(unittest.TestCase):
    def test_overlap_deduplication(self):
        self.assertEqual("Назовите код из SMS пожалуйста", overlap_deduplicate("Назовите код из SMS", "из SMS пожалуйста"))
    def test_caller_priority_over_user(self):
        p=DualChannelPipeline(lambda b:b.decode()); p.ingest(USER,b"user",0,1); p.ingest(CALLER,b"caller",0,1)
        self.assertEqual(CALLER,p.drain_once().speaker); self.assertEqual(USER,p.drain_once().speaker)
    def test_chronological_assembly(self):
        a=ConversationAssembler(); a.emit(USER,"what happened",5800,6500); a.emit(CALLER,"bank call",3200,5200)
        self.assertEqual([CALLER,USER],[x.speaker for x in a.turns])
    def test_mic_leak_is_suppressed(self):
        a=ConversationAssembler(); a.emit(CALLER,"назовите код из sms",1000,3000); user=a.emit(USER,"назовите код из sms",1200,3100)
        self.assertTrue(a.suppress_mic_leak(user)); self.assertTrue(user.metadata["probableMicLeak"])
    def test_analysis_coalesces_while_inflight(self):
        s=AnalysisScheduler(); a=Utterance("1",CALLER,"one",0,1); b=Utterance("2",CALLER,"two",1,2)
        self.assertTrue(s.offer([a])); self.assertFalse(s.offer([b])); self.assertEqual([a,b],s.complete())
    def test_user_work_does_not_block_caller_metric(self):
        p=DualChannelPipeline(lambda b:b.decode()); [p.ingest(USER,b"u",i,i+1) for i in range(4)]; p.ingest(CALLER,b"c",9,10)
        p.drain_once(); self.assertEqual(CALLER,p.metrics[-1]["speaker"])
    def test_risk_state_schema_and_payload(self):
        state=CallRiskState(credential_request=True,risk_level="CRITICAL"); turn=Utterance("x",CALLER,"give code",0,1)
        payload=AnalysisScheduler().payload(state,[turn],{"source":"SYSTEM_MIX_GUARDED"})
        self.assertTrue(payload["previousState"]["credential_request"]); self.assertEqual(CALLER,payload["newUtterances"][0]["speaker"])

    def test_overlapping_windows_emit_only_new_stable_words(self):
        p=DualChannelPipeline(lambda b:b.decode())
        p.ingest(CALLER,b"one two",0,1000); first=p.drain_once()
        p.ingest(CALLER,b"two three",500,1500); second=p.drain_once()
        self.assertEqual("one two", first.text)
        self.assertEqual("three", second.text)
        self.assertEqual("one two three", " ".join(turn.text for turn in p.assembler.turns))

    def test_silent_real_pcm_is_not_enqueued(self):
        p=DualChannelPipeline(lambda b:"unused")
        self.assertFalse(p.ingest(CALLER, b"\0" * 9600, 0, 100))
        self.assertIsNone(p.drain_once())

    def test_bounded_caller_queue_replaces_stale_window(self):
        scheduler=PriorityASRScheduler(max_items=1)
        self.assertTrue(scheduler.submit(AudioWork(CALLER,b"old",0,1,Timing(0))))
        self.assertTrue(scheduler.submit(AudioWork(CALLER,b"new",1,2,Timing(0))))
        self.assertEqual(1,scheduler.dropped_caller)
        self.assertEqual(b"new",scheduler.next().pcm)
