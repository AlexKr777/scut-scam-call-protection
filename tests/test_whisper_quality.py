import unittest

from backend.whisper_quality import decode_with_optional_retry


class WhisperQualityTests(unittest.TestCase):
    def test_empty_meaningful_first_decode_retries_once_and_selects_nonempty_candidate(self):
        first = {"text": "", "averageLogProb": "-1.2", "noSpeechProbability": "0.7", "compressionRatio": "0.0", "language": "ru", "languageProbability": "0.8", "segments": []}
        retry = {"text": "назовите код", "averageLogProb": "-0.2", "noSpeechProbability": "0.01", "compressionRatio": "1.1", "language": "ru", "languageProbability": "0.9", "segments": []}
        responses = iter([first, retry])

        result = decode_with_optional_retry(b"first", b"retry", 2.0, lambda pcm: next(responses))

        self.assertTrue(result["retry_occurred"])
        self.assertEqual("retry", result["selected"])
        self.assertEqual("назовите код", result["text"])
        self.assertEqual("empty_meaningful_audio", result["retry_reason"])

    def test_healthy_decode_does_not_retry(self):
        healthy = {"text": "spune codul", "averageLogProb": "-0.2", "noSpeechProbability": "0.01", "compressionRatio": "1.1", "language": "ro", "languageProbability": "0.9", "segments": []}
        calls = []

        result = decode_with_optional_retry(b"first", b"retry", 2.0, lambda pcm: calls.append(pcm) or healthy)

        self.assertFalse(result["retry_occurred"])
        self.assertEqual("first", result["selected"])
        self.assertEqual([b"first"], calls)

    def test_selection_rejects_pathological_retry_without_external_evidence(self):
        first = {"text": "read the code", "averageLogProb": "-1.1", "noSpeechProbability": "0.1", "compressionRatio": "1.1", "language": "en", "languageProbability": "0.8", "segments": []}
        retry = {"text": "code code code code code code code", "averageLogProb": "-0.1", "noSpeechProbability": "0.01", "compressionRatio": "3.1", "language": "en", "languageProbability": "0.9", "segments": []}
        responses = iter([first, retry])

        result = decode_with_optional_retry(b"first", b"retry", 2.0, lambda pcm: next(responses))

        self.assertTrue(result["retry_occurred"])
        self.assertEqual("first", result["selected"])
        self.assertEqual("first_candidate_higher_asr_quality", result["selection_reason"])
