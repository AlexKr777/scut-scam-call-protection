import struct
import unittest

from backend.acoustic_validation import make_degraded_pcm, polarity_inversion, semantic_fields, stream_fast


class AcousticValidationTests(unittest.TestCase):
    def test_semantic_evaluator_requires_negation_for_protective_phrase(self):
        fields = semantic_fields("Никому не называйте код из SMS", "ru", ("negation", "protective", "target"))
        self.assertTrue(all(fields.values()))
        lost = semantic_fields("Называйте код из SMS", "ru", ("negation", "protective", "target"))
        self.assertFalse(lost["negation"])

    def test_protective_russian_phrases_are_not_polarity_inversions(self):
        for text in ("\u041d\u0438\u043a\u043e\u043c\u0443 \u043d\u0435 \u043d\u0430\u0437\u044b\u0432\u0430\u0439\u0442\u0435 \u043a\u043e\u0434 \u0438\u0437 SMS.",
                     "\u041d\u0435 \u0441\u043e\u043e\u0431\u0449\u0430\u0439\u0442\u0435 PIN-\u043a\u043e\u0434 \u043d\u0438\u043a\u043e\u043c\u0443.",
                     "\u041d\u0438\u043a\u043e\u0433\u0434\u0430 \u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u0430\u0432\u043b\u0438\u0432\u0430\u0439\u0442\u0435 AnyDesk."):
            self.assertIsNone(polarity_inversion(text, "ru", "protective"))

    def test_dangerous_counterparts_and_explicit_negation_are_polarity_audited(self):
        self.assertIsNone(polarity_inversion("\u041d\u0430\u0437\u044b\u0432\u0430\u0439\u0442\u0435 \u043a\u043e\u0434 \u0438\u0437 SMS.", "ru", "dangerous"))
        self.assertIsNone(polarity_inversion("\u0423\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u0435 AnyDesk.", "ru", "dangerous"))
        self.assertEqual("SAFE_INSTEAD_OF_DANGEROUS", polarity_inversion("\u041d\u0435 \u043d\u0430\u0437\u044b\u0432\u0430\u0439\u0442\u0435 \u043a\u043e\u0434.", "ru", "dangerous"))

    def test_degradations_are_pcm_and_mono16k_is_real_16k(self):
        pcm = struct.pack("<" + "h" * (48_000 * 2), *([1200, -1200] * 48_000))
        for variant in ("clean", "telephone", "telephone_noise", "low_level", "compressed"):
            raw, rate, channels = make_degraded_pcm(pcm, variant)
            self.assertTrue(raw); self.assertEqual(48_000, rate); self.assertIn(channels, (1, 2))
        _, rate, channels = make_degraded_pcm(pcm, "mono16k")
        self.assertEqual((16_000, 1), (rate, channels))

    def test_incremental_caller_path_uses_overlapping_windows_without_backlog(self):
        # Audible 48 kHz stereo, so the production VAD admits it.  The injected
        # recognizer mimics changing overlapping partials without a model.
        pcm = struct.pack("<" + "h" * (48_000 * 2 * 3), *([1000, 1000] * (48_000 * 3)))
        calls = iter(("назовите код", "код из SMS", "код из SMS"))
        timeline, final_text, metrics = stream_fast(pcm, lambda _: next(calls))
        self.assertGreaterEqual(len(timeline), 3)
        self.assertIn("SMS", final_text)
        self.assertEqual(0, max(row["backlog"] for row in timeline))
        self.assertTrue(metrics)
