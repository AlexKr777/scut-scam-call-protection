import unittest

from backend.realtime_pipeline import StreamingTranscriptStabilizer


def hypothesis(text, start, end, **metadata):
    return {"text": text, "start_ms": start, "end_ms": end, **metadata}


class StreamingTranscriptStabilizerTests(unittest.TestCase):
    def test_overlapping_windows_same_utterance_do_not_create_duplicate_turns(self):
        stabilizer = StreamingTranscriptStabilizer()
        stabilizer.process(hypothesis("one two", 0, 2000))
        event = stabilizer.process(hypothesis("two three", 1000, 3000), end_of_stream=True)
        self.assertEqual("one two three", event.committed_text)
        self.assertEqual(["one two three"], stabilizer.committed_texts)

    def test_hypothesis_revision_updates_the_provisional_text(self):
        stabilizer = StreamingTranscriptStabilizer()
        stabilizer.process(hypothesis("share the cod", 0, 2000))
        event = stabilizer.process(hypothesis("share the code", 1000, 3000))
        self.assertEqual("share the code", event.provisional_text)
        self.assertEqual("REVISED", event.action)

    def test_tail_only_overlap_is_a_revision_not_a_duplicate_suffix(self):
        stabilizer = StreamingTranscriptStabilizer()
        stabilizer.process(hypothesis("Tell me the code from the SMS", 0, 2000))
        event = stabilizer.process(hypothesis("from the SMS.", 1000, 2789), end_of_stream=True)
        self.assertEqual("Tell me the code from the SMS", event.committed_text)

    def test_end_of_speech_commits_exactly_one_turn(self):
        stabilizer = StreamingTranscriptStabilizer()
        stabilizer.process(hypothesis("call the bank", 0, 1000))
        event = stabilizer.process(hypothesis("call the bank", 500, 1500), end_of_stream=True)
        self.assertEqual("COMMITTED", event.action)
        self.assertEqual(["call the bank"], stabilizer.committed_texts)

    def test_true_second_utterance_becomes_a_second_turn(self):
        stabilizer = StreamingTranscriptStabilizer()
        stabilizer.process(hypothesis("first utterance", 0, 1000))
        event = stabilizer.process(hypothesis("second utterance", 1600, 2500), end_of_stream=True)
        self.assertEqual("NEW_PROVISIONAL", event.action)
        self.assertEqual(["first utterance", "second utterance"], stabilizer.committed_texts)

    def test_genuine_language_switch_after_boundary_is_accepted(self):
        stabilizer = StreamingTranscriptStabilizer()
        stabilizer.process(hypothesis("Назовите код", 0, 1000, language="ru", languageProbability="0.99"))
        stabilizer.process(hypothesis("Tell me the code", 1600, 2600, language="en", languageProbability="0.99"), end_of_stream=True)
        self.assertEqual(["Назовите код", "Tell me the code"], stabilizer.committed_texts)

    def test_russian_to_romanian_code_switch_after_boundary_is_accepted(self):
        stabilizer = StreamingTranscriptStabilizer()
        stabilizer.process(hypothesis("Назовите код", 0, 1000, language="ru"))
        stabilizer.process(hypothesis("Spune codul", 1600, 2600, language="ro"), end_of_stream=True)
        self.assertEqual(["Назовите код", "Spune codul"], stabilizer.committed_texts)

    def test_romanian_to_russian_code_switch_after_boundary_is_accepted(self):
        stabilizer = StreamingTranscriptStabilizer()
        stabilizer.process(hypothesis("Spune codul", 0, 1000, language="ro"))
        stabilizer.process(hypothesis("Назовите код", 1600, 2600, language="ru"), end_of_stream=True)
        self.assertEqual(["Spune codul", "Назовите код"], stabilizer.committed_texts)

    def test_low_confidence_overlapping_language_flip_is_not_a_fake_turn(self):
        stabilizer = StreamingTranscriptStabilizer()
        stabilizer.process(hypothesis("Назовите код из SMS.", 0, 2000, language="ru", languageProbability="0.98", averageLogProb="-0.2", noSpeechProbability="0.01"))
        event = stabilizer.process(hypothesis("This is a miss.", 1000, 2734, language="en", languageProbability="0.4866", averageLogProb="-0.9163", noSpeechProbability="0.3538"), end_of_stream=True)
        self.assertEqual("IGNORED_OVERLAP", event.action)
        self.assertEqual(["Назовите код из SMS."], stabilizer.committed_texts)
        self.assertIn("weak_overlapping_disagreement", event.reason)

    def test_end_of_stream_finalizes_last_provisional_turn(self):
        stabilizer = StreamingTranscriptStabilizer()
        event = stabilizer.process(hypothesis("last words", 0, 1000), end_of_stream=True)
        self.assertEqual("COMMITTED", event.action)
        self.assertEqual(["last words"], stabilizer.committed_texts)

    def test_nomic_context_is_committed_history_plus_one_provisional_turn(self):
        stabilizer = StreamingTranscriptStabilizer()
        stabilizer.process(hypothesis("first", 0, 1000), end_of_stream=True)
        stabilizer.process(hypothesis("second", 1500, 2500))
        self.assertEqual([("CALLER", "first"), ("CALLER", "second")], stabilizer.nomic_turns("CALLER"))

    def test_previous_committed_conversation_is_never_lost(self):
        stabilizer = StreamingTranscriptStabilizer()
        stabilizer.process(hypothesis("first", 0, 1000), end_of_stream=True)
        stabilizer.process(hypothesis("second", 1500, 2500), end_of_stream=True)
        self.assertEqual("first second", stabilizer.committed_transcript)
