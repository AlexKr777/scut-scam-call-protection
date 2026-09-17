import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import audio_replay
from scripts import audio_replay as audio_replay_cli


class AudioReplayTests(unittest.TestCase):
    def test_utterance_replay_decodes_full_vad_segment_once_then_scores_one_final_turn(self):
        voiced = struct.pack("<" + "h" * (48_000 * 2), *([1000, 1000] * 48_000))
        silence = b"\0" * (48_000 * 2 * 2)
        engine = object.__new__(audio_replay.AudioReplayEngine)
        engine.preflight, engine.logger = {"threshold": 0.6}, lambda _: None
        engine.nomic = unittest.mock.Mock()
        engine.nomic.adapter.tokenizer.return_value = {"input_ids": [1, 2]}
        engine.nomic.score.return_value = unittest.mock.Mock(action_score=0.8, semantic_scores={}, kind_scores={})
        case = {"case_id": "utterance", "audio_path": "unused.wav", "expected_class": "dangerous", "reference_transcript": "final text", "reference_transcript_clip_aligned": True}
        with patch.object(audio_replay, "load_pcm", return_value=(voiced + silence, 3.0)), patch("backend.guarded_audio.transcribe_pcm_details", return_value={"text": "final text", "language": "ru", "languageProbability": "0.99", "segments": []} ) as transcribe:
            result = engine.replay(case)
        self.assertEqual(1, transcribe.call_count)
        self.assertEqual("vad_silence", result["whisper"]["utterances"][0]["finalization_reason"])
        self.assertEqual(["final text"], [event["text"] for event in result["ui_events"]])
        self.assertEqual(1, len(result["nomic"]["timeline"]))
        self.assertEqual("final text", result["nomic"]["timeline"][0]["transcript"])
        self.assertEqual({"vad_frame_ms": 250, "endpoint_silence_ms": 750, "max_utterance_ms": 12_000}, {key: result["segmentation"][key] for key in ("vad_frame_ms", "endpoint_silence_ms", "max_utterance_ms")})

    def test_v2_retry_replay_emits_only_selected_final_transcript_and_one_nomic_turn(self):
        voiced = struct.pack("<" + "h" * (48_000 * 2), *([1000, 1000] * 48_000))
        silence = b"\0" * (48_000 * 2 * 2)
        engine = object.__new__(audio_replay.AudioReplayEngine)
        engine.preflight, engine.logger = {"threshold": 0.6}, lambda _: None
        engine.nomic = unittest.mock.Mock()
        engine.nomic.adapter.tokenizer.return_value = {"input_ids": [1, 2]}
        engine.nomic.score.return_value = unittest.mock.Mock(action_score=0.8, semantic_scores={}, kind_scores={})
        case = {"case_id": "retry", "audio_path": "unused.wav", "expected_class": "dangerous", "reference_transcript": "retry text", "reference_transcript_clip_aligned": True}
        first = {"text": "", "language": "ru", "languageProbability": "0.9", "averageLogProb": "-1.2", "noSpeechProbability": "0.7", "compressionRatio": "0.0", "segments": []}
        retry = {"text": "retry text", "language": "ru", "languageProbability": "0.9", "averageLogProb": "-0.2", "noSpeechProbability": "0.01", "compressionRatio": "1.1", "segments": []}
        with patch.object(audio_replay, "load_pcm", return_value=(voiced + silence, 3.0)), patch("backend.guarded_audio.transcribe_pcm_details", side_effect=[first, retry]) as transcribe:
            result = engine.replay_whisper_quality_v2(case)

        self.assertEqual(2, transcribe.call_count)
        self.assertEqual(["retry text"], [event["text"] for event in result["ui_events"]])
        self.assertEqual(1, len(result["nomic"]["timeline"]))
        self.assertEqual("retry text", result["nomic"]["timeline"][0]["transcript"])
        self.assertTrue(result["whisper"]["utterances"][0]["retry_occurred"])
        self.assertEqual("retry", result["whisper"]["utterances"][0]["selected"])

    def test_utterance_replay_keeps_prior_turns_and_redetects_language_per_turn(self):
        frame = struct.pack("<" + "h" * (48_000 // 2), *([1000, 1000] * (48_000 // 4)))
        silence = b"\0" * len(frame)
        engine = object.__new__(audio_replay.AudioReplayEngine)
        engine.preflight, engine.logger = {"threshold": 0.6}, lambda _: None
        engine.nomic = unittest.mock.Mock()
        engine.nomic.adapter.tokenizer.return_value = {"input_ids": [1]}
        seen_turns = []
        def score(turns):
            seen_turns.append(list(turns))
            return unittest.mock.Mock(action_score=0.1, semantic_scores={}, kind_scores={})
        engine.nomic.score.side_effect = score
        case = {"case_id": "switch", "audio_path": "unused.wav", "expected_class": "protective", "reference_transcript": "", "reference_transcript_clip_aligned": False}
        results = [{"text": "назовите код", "language": "ru", "languageProbability": "0.99", "segments": []}, {"text": "Spune codul", "language": "ro", "languageProbability": "0.99", "segments": []}]
        with patch.object(audio_replay, "load_pcm", return_value=(frame + silence * 3 + frame + silence * 3, 2.0)), patch("backend.guarded_audio.transcribe_pcm_details", side_effect=results) as transcribe:
            result = engine.replay(case)
        self.assertEqual(2, transcribe.call_count)
        self.assertTrue(all("language" not in call.kwargs for call in transcribe.call_args_list))
        self.assertEqual([[("CALLER", "назовите код")], [("CALLER", "назовите код"), ("CALLER", "Spune codul")]], seen_turns)
        self.assertEqual(["ru", "ro"], [item["language"] for item in result["whisper"]["utterances"]])
        self.assertEqual(["назовите код", "Spune codul"], [event["text"] for event in result["ui_events"]])

    def test_manifest_defaults_to_non_strict_and_lock_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "case.wav"
            audio.write_bytes(b"fixture-audio")
            manifest = [{"case_id": "case", "audio_path": str(audio), "expected_class": "dangerous"}]
            locked = audio_replay.lock_manifest(manifest)
            self.assertFalse(locked["cases"][0]["strict_score_eligible"])
            self.assertEqual(locked["pack_sha256"], audio_replay.lock_manifest(manifest)["pack_sha256"])

    def test_atomic_status_replaces_complete_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "status.json"
            audio_replay.atomic_json_write(path, {"state": "RUNNING", "completed_cases": 1})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["state"], "RUNNING")

    def test_scoring_excludes_non_strict_and_two_party_cases(self):
        rows = [
            {"strict_score_eligible": True, "capture_equivalence": "PRODUCTION_EQUIVALENT", "expected_class": "dangerous", "triggered": True},
            {"strict_score_eligible": True, "capture_equivalence": "TWO_PARTY_STRESS_TEST", "expected_class": "dangerous", "triggered": False},
            {"strict_score_eligible": False, "capture_equivalence": "PRODUCTION_EQUIVALENT", "expected_class": "protective", "triggered": True},
        ]
        self.assertEqual(audio_replay.confusion_matrix(rows, "PRODUCTION_EQUIVALENT"), {"TP": 1, "FP": 0, "FN": 0, "TN": 0})

    def test_first_crossing_is_not_repeated(self):
        timeline = [{"audio_timestamp_sec": 1.0, "action_score": 0.4}, {"audio_timestamp_sec": 2.0, "action_score": 0.7}, {"audio_timestamp_sec": 3.0, "action_score": 0.9}]
        self.assertEqual(audio_replay.first_threshold_crossing(timeline, 0.6), 2.0)

    def test_wer_is_na_when_reference_is_not_clip_aligned(self):
        self.assertEqual(audio_replay.error_rates("one two", "one", False), {"WER": None, "CER": None})
        self.assertEqual(audio_replay.error_rates("one two", "one two", True), {"WER": 0.0, "CER": 0.0})

    def test_demo_command_preserves_case_id_and_uses_realtime_without_reports(self):
        args = audio_replay_cli.build_parser().parse_args(["demo", "synthetic_ru_01_dangerous"])
        case = {"case_id": "synthetic_ru_01_dangerous", "expected_class": "dangerous"}
        engine = unittest.mock.Mock()
        engine.replay.return_value = {"case_id": case["case_id"], "expected_class": "dangerous", "whisper": {"final_transcript": "spoken", "latency_sec": 0.1, "real_time_factor": 0.1}, "nomic": {"max_score": 0.8, "timeline": [{"rolling_transcript": "spoken"}]}, "alert": {"triggered": True, "first_alert_sec": 2.0}}
        with patch.object(audio_replay_cli, "verify_preflight", return_value={"threshold": 0.6}), patch.object(audio_replay_cli, "_load_cases", return_value=[case]), patch.object(audio_replay_cli, "AudioReplayEngine", return_value=engine), patch.object(audio_replay_cli, "write_reports") as reports:
            self.assertEqual(args.func(args), 0)
        engine.replay.assert_called_once_with(case, realtime=True)
        reports.assert_not_called()
