import unittest

from backend.realtime_pipeline import CallerUtteranceBuffer


class CallerUtteranceBufferTests(unittest.TestCase):
    def setUp(self):
        self.buffer = CallerUtteranceBuffer(endpoint_silence_ms=750, max_utterance_ms=12_000)

    def test_buffers_audio_without_emitting_until_a_vad_boundary(self):
        self.assertEqual([], self.buffer.ingest(b"first", 0, 250, voiced=True))
        self.assertEqual([], self.buffer.ingest(b"second", 250, 500, voiced=True))
        self.assertEqual([], self.buffer.ingest(b"pause", 500, 1000, voiced=False))
        finalized = self.buffer.ingest(b"pause", 1000, 1250, voiced=False)

        self.assertEqual(1, len(finalized))
        self.assertEqual(b"firstsecondpaus", finalized[0].pcm)
        self.assertEqual((0, 500), (finalized[0].start_ms, finalized[0].end_ms))
        self.assertEqual("vad_silence", finalized[0].reason)

    def test_preserves_all_pcm_between_speech_frames_for_one_utterance(self):
        self.buffer.ingest(b"speech-a", 0, 250, voiced=True)
        self.buffer.ingest(b"natural-pause", 250, 500, voiced=False)
        self.buffer.ingest(b"speech-b", 500, 750, voiced=True)
        finalized = self.buffer.finish(750)

        self.assertEqual(1, len(finalized))
        self.assertEqual(b"speech-anatural-pausespeech-b", finalized[0].pcm)
        self.assertEqual("end_of_stream", finalized[0].reason)

    def test_maximum_duration_finalizes_continuous_speech_without_overlap(self):
        buffer = CallerUtteranceBuffer(endpoint_silence_ms=750, max_utterance_ms=1_000)
        self.assertEqual([], buffer.ingest(b"a", 0, 500, voiced=True))
        finalized = buffer.ingest(b"b", 500, 1_000, voiced=True)

        self.assertEqual(1, len(finalized))
        self.assertEqual(b"ab", finalized[0].pcm)
        self.assertEqual("max_duration", finalized[0].reason)
        self.assertEqual([], buffer.finish(1_000))

    def test_end_of_stream_finalizes_once_and_never_duplicates_audio(self):
        self.buffer.ingest(b"speech", 0, 250, voiced=True)
        self.assertEqual([b"speech"], [item.pcm for item in self.buffer.finish(250)])
        self.assertEqual([], self.buffer.finish(250))

    def test_first_decode_pcm_includes_preroll_and_existing_endpoint_postroll(self):
        buffer = CallerUtteranceBuffer(endpoint_silence_ms=750, max_utterance_ms=12_000)
        buffer.ingest(b"p" * 250, 0, 250, voiced=False)
        buffer.ingest(b"s" * 250, 250, 500, voiced=True)
        buffer.ingest(b"t" * 250, 500, 750, voiced=False)
        buffer.ingest(b"t" * 250, 750, 1000, voiced=False)
        finalized = buffer.ingest(b"t" * 250, 1000, 1250, voiced=False)

        self.assertEqual(1, len(finalized))
        self.assertEqual(b"p" * 250 + b"s" * 250 + b"t" * 400, finalized[0].pcm)
        self.assertEqual(b"p" * 250 + b"s" * 250 + b"t" * 700, finalized[0].retry_pcm)
        self.assertEqual((0, 500), (finalized[0].start_ms, finalized[0].end_ms))

    def test_hard_cap_starts_clean_next_utterance_without_duplicate_pcm(self):
        buffer = CallerUtteranceBuffer(endpoint_silence_ms=750, max_utterance_ms=1_000)
        buffer.ingest(b"a", 0, 500, voiced=True)
        first = buffer.ingest(b"b", 500, 1000, voiced=True)
        buffer.ingest(b"c", 1000, 1500, voiced=True)
        second = buffer.finish(1500)

        self.assertEqual([b"ab"], [item.pcm for item in first])
        self.assertEqual([b"c"], [item.pcm for item in second])
