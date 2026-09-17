"""Build the V2 acceptance artifacts from immutable baseline and V2 replay outputs."""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "reports" / "audio_replay_v1_utterance_whisper" / "SCUT_AUDIO_REPLAY_V1_UTTERANCE_WHISPER_RESULTS.json"
RESULTS = ROOT / "reports" / "whisper_quality_v2" / "SCUT_WHISPER_QUALITY_V2_RESULTS.json"
RAW_V2 = RESULTS.with_name("SCUT_WHISPER_QUALITY_V2_REPLAY_RAW.json")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil((len(ordered) - 1) * fraction))]


def main() -> None:
    baseline, v2 = load(BASELINE), load(RAW_V2)
    old = {row["case_id"]: row for row in baseline["calls"]}
    comparisons = []
    for row in v2["calls"]:
        previous = old[row["case_id"]]
        comparisons.append({"case_id": row["case_id"], "old_WER": previous["whisper"]["WER"], "new_WER": row["whisper"]["WER"],
                            "old_CER": previous["whisper"]["CER"], "new_CER": row["whisper"]["CER"],
                            "outcome": "improved" if row["whisper"]["WER"] < previous["whisper"]["WER"] else "regressed" if row["whisper"]["WER"] > previous["whisper"]["WER"] else "unchanged"})
    utterances = [item for row in v2["calls"] for item in row["whisper"]["utterances"]]
    retried = [item for item in utterances if item["retry_occurred"]]
    retry_wins = [item for item in retried if item["selected"] == "retry"]
    retry_losses = [item for item in retried if item["selected"] == "first"]
    probes = []
    for case_id in ("synthetic_ru_03_dangerous", "synthetic_ru_07_dangerous", "synthetic_ru_08_dangerous", "synthetic_ru_09_dangerous"):
        row, previous = next(item for item in v2["calls"] if item["case_id"] == case_id), old[case_id]
        utterance = row["whisper"]["utterances"][0]
        probes.append({"case_id": case_id, "source_transcript": row["reference_transcript"], "previous_utterance_pipeline_transcript": previous["whisper"]["final_transcript"],
                       "new_transcript": row["whisper"]["final_transcript"], "previous_WER": previous["whisper"]["WER"], "new_WER": row["whisper"]["WER"],
                       "previous_CER": previous["whisper"]["CER"], "new_CER": row["whisper"]["CER"], "retry_occurred": utterance["retry_occurred"],
                       "first_decode_diagnostics": utterance["first_decode"], "retry_decode_diagnostics": utterance["retry_decode"],
                       "selected": utterance["selected"], "decode_latency_sec": utterance["transcription_latency_sec"]})
    old_wer = [row["whisper"]["WER"] for row in baseline["calls"] if row["whisper"]["WER"] is not None]
    new_wer = [row["whisper"]["WER"] for row in v2["calls"] if row["whisper"]["WER"] is not None]
    summary = {"old_mean_WER": baseline["asr_metrics"]["mean_WER"], "new_mean_WER": v2["asr_metrics"]["mean_WER"],
               "old_median_WER": baseline["asr_metrics"]["median_WER"], "new_median_WER": v2["asr_metrics"]["median_WER"],
               "old_p95_WER": percentile(old_wer, .95), "new_p95_WER": percentile(new_wer, .95),
               "old_exact_match_count": sum(value == 0 for value in old_wer), "new_exact_match_count": sum(value == 0 for value in new_wer),
               "improved_cases": sum(item["outcome"] == "improved" for item in comparisons), "unchanged_cases": sum(item["outcome"] == "unchanged" for item in comparisons), "regressed_cases": sum(item["outcome"] == "regressed" for item in comparisons),
               "retry_rate": round(len(retried) / len(utterances), 4) if utterances else None, "retry_win_rate": round(len(retry_wins) / len(retried), 4) if retried else None, "retry_loss_rate": round(len(retry_losses) / len(retried), 4) if retried else None,
               "old_end_to_final_p50_sec": baseline["asr_metrics"]["utterance_end_to_whisper_p50_sec"], "old_end_to_final_p95_sec": baseline["asr_metrics"]["utterance_end_to_whisper_p95_sec"],
               "new_end_to_final_p50_sec": v2["asr_metrics"]["utterance_end_to_whisper_p50_sec"], "new_end_to_final_p95_sec": v2["asr_metrics"]["utterance_end_to_whisper_p95_sec"],
               "normal_decode_p50_sec": percentile([item["first_decode_latency_sec"] for item in utterances], .5), "normal_decode_p95_sec": percentile([item["first_decode_latency_sec"] for item in utterances], .95),
               "retry_decode_p50_sec": percentile([item["retry_decode_latency_sec"] for item in retried], .5), "retry_decode_p95_sec": percentile([item["retry_decode_latency_sec"] for item in retried], .95)}
    result = {"verdict": "SCUT_WHISPER_QUALITY_V2_READY" if summary["new_mean_WER"] <= summary["old_mean_WER"] and summary["regressed_cases"] == 0 else "SCUT_WHISPER_QUALITY_V2_KEEP_BASELINE",
              "scope": {"nomic_modified": False, "threshold": v2["provenance"]["threshold"], "checkpoint_sha256": v2["provenance"]["checkpoint_sha256"], "locked_pack_sha256": load(ROOT / "data" / "audio_replay_v1" / "audio_replay_v1_manifest.lock.json")["pack_sha256"]},
              "boundary_contract": {"whole_utterance": True, "provisional_transcripts": False, "pre_roll_ms": 250, "post_roll_ms": 400, "retry_pre_roll_ms": 500, "retry_post_roll_ms": 700, "endpoint_silence_ms": 750, "max_utterance_ms": 12000, "language_detection": "per_utterance", "one_final_transcript_per_utterance": True, "one_nomic_evaluation_per_utterance": True},
              "real_call_audio_available": 0, "real_audio_note": "Local WAV inventory contains synthetic fixtures, diagnostics, and dependency fixtures; no directly usable, attributed real call audio is available.",
              "summary": summary, "case_comparison": comparisons, "known_probes": probes, "raw_v2_replay": "SCUT_WHISPER_QUALITY_V2_REPLAY_RAW.json"}
    RAW_V2.write_text(json.dumps(v2, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    RESULTS.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# SCUT Whisper Quality V2", "", f"## Verdict\n\n{result['verdict']}", "", "## Locked replay comparison", "", "| Metric | Current utterance baseline | V2 |", "|---|---:|---:|",
             f"| Mean WER | {summary['old_mean_WER']:.4f} | {summary['new_mean_WER']:.4f} |", f"| Median WER | {summary['old_median_WER']:.4f} | {summary['new_median_WER']:.4f} |", f"| p95 WER | {summary['old_p95_WER']:.4f} | {summary['new_p95_WER']:.4f} |", f"| Exact matches | {summary['old_exact_match_count']} | {summary['new_exact_match_count']} |", f"| End→FINAL p50 (s) | {summary['old_end_to_final_p50_sec']:.4f} | {summary['new_end_to_final_p50_sec']:.4f} |", f"| End→FINAL p95 (s) | {summary['old_end_to_final_p95_sec']:.4f} | {summary['new_end_to_final_p95_sec']:.4f} |", "", f"Improved / unchanged / regressed: {summary['improved_cases']} / {summary['unchanged_cases']} / {summary['regressed_cases']}. Retry rate: {summary['retry_rate']:.2%}; retry win/loss rates: {summary['retry_win_rate']} / {summary['retry_loss_rate']}.", "", "## Boundary and contract", "", "- First decode PCM: 250 ms raw pre-roll plus 400 ms of already-buffered endpoint silence; no additional endpoint wait.", "- Retry PCM: up to 500 ms pre-context plus 700 ms existing post-context; one optional ASR-only retry.", "- VAD: 250 ms frames, 750 ms endpoint, 12 s cap. Language detection is per utterance. Only one selected `FINAL_TRANSCRIPT` reaches one Nomic evaluation.", "", "## Known RU probes", ""]
    for probe in probes:
        lines.extend([f"### {probe['case_id']}", "", f"- Previous → new WER/CER: {probe['previous_WER']:.4f}/{probe['previous_CER']:.4f} → {probe['new_WER']:.4f}/{probe['new_CER']:.4f}", f"- Retry: {probe['retry_occurred']}; selected: {probe['selected']}; decode latency: {probe['decode_latency_sec']:.4f}s.", f"- Source: {probe['source_transcript']}", f"- Previous: {probe['previous_utterance_pipeline_transcript']}", f"- New: {probe['new_transcript']}", ""])
    lines.extend(["## Provenance", "", f"- Locked pack SHA-256: {result['scope']['locked_pack_sha256']}", f"- Nomic checkpoint SHA-256: {result['scope']['checkpoint_sha256']}; threshold: {result['scope']['threshold']}", "- Nomic model, threshold, architecture, data, alerts, and semantic logic were not modified.", "- REAL_CALL_AUDIO_AVAILABLE = 0.", ""])
    RESULTS.with_name("SCUT_WHISPER_QUALITY_V2_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
