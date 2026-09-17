"""Write an evidence-only V1 versus transcript-stabilizer comparison."""
from __future__ import annotations
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.audio_replay import atomic_json_write, metrics


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    return round(sorted(values)[round((len(values) - 1) * fraction)], 4)


def snapshot(rows: list[dict], stabilized: bool) -> dict:
    nomic_latency = [event["inference_latency_sec"] for row in rows for event in row["nomic"].get("timeline", [])]
    wer = [row["whisper"]["WER"] for row in rows if row["whisper"].get("WER") is not None]
    alerts = [row["first_alert_sec"] for row in rows if row.get("first_alert_sec") is not None]
    if stabilized:
        duplicate_turns = sum(max(0, sum(bool(window.get("committed_text")) for window in row["whisper"].get("windows", [])) - 1) for row in rows)
        tails: int | str = sum(1 for row in rows for window in row["whisper"].get("windows", []) if window.get("stabilizer_action") == "IGNORED_OVERLAP" and window.get("stabilizer_reason") == "weak_overlapping_disagreement")
    else:
        # Every V1 fixture is a single synthetic utterance; excess permanent
        # Nomic events are therefore overlap turns, but V1 did not persist raw
        # window metadata sufficient to count hallucinated tails individually.
        duplicate_turns, tails = sum(max(0, len(row["nomic"].get("timeline", [])) - 1) for row in rows), "NOT_INSTRUMENTED_IN_V1"
    return {
        "confusion": metrics(rows)["PRODUCTION_EQUIVALENT"], "wer_mean": round(statistics.mean(wer), 4),
        "max_nomic_score_p50": percentile([row["nomic"]["max_score"] for row in rows if row["nomic"].get("max_score") is not None], .5),
        "nomic_latency_p50_sec": percentile(nomic_latency, .5), "nomic_latency_p95_sec": percentile(nomic_latency, .95),
        "whisper_latency_p50_sec": percentile([row["whisper"]["latency_sec"] for row in rows], .5),
        "whisper_latency_p95_sec": percentile([row["whisper"]["latency_sec"] for row in rows], .95),
        "alert_time_p50_sec": percentile(alerts, .5), "duplicate_overlap_turn_count": duplicate_turns,
        "hallucinated_tail_count": tails,
    }


def main() -> None:
    before = [json.loads(path.read_text(encoding="utf-8")) for path in (ROOT / "reports" / "audio_replay_v1" / "calls").glob("*.json")]
    after_path = ROOT / "reports" / "audio_replay_v1_stabilizer_v3" / "SCUT_AUDIO_REPLAY_V1_STABILIZER_V3_RESULTS.json"
    after = json.loads(after_path.read_text(encoding="utf-8"))["calls"]
    report = {"schema_version": 1, "pack_sha256": "3ABD874C7C05F6C4BE90327361E0D87B5FAB2533BC8D046BAC7333DDE7F8EE42", "before": snapshot(before, False), "after": snapshot(after, True), "interpretation": "V3 removes permanent duplicate overlap turns. Metrics are descriptive; corrected Nomic input is intentionally not comparable to V1's duplicated overlap input as an unchanged decision path."}
    output = after_path.with_name("SCUT_AUDIO_REPLAY_V1_STABILIZER_COMPARISON.json")
    atomic_json_write(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
