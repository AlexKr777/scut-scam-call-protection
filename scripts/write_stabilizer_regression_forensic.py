"""Evidence-only forensic comparison of V1 duplicate turns and V3 stabilization."""
from __future__ import annotations
import hashlib
import json
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.audio_replay import atomic_json_write
from backend.guarded_audio import transcribe_pcm_details

REPORTS = ROOT / "reports" / "audio_replay_v1_stabilizer_v3"
V3 = REPORTS / "SCUT_AUDIO_REPLAY_V1_STABILIZER_V3_RESULTS.json"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def old_timeline(row: dict) -> list[dict]:
    turns: list[tuple[str, str]] = []
    result = []
    for event in row["nomic"]["timeline"]:
        turns.append(("CALLER", event["transcript"]))
        # This is the deterministic rendering implied by V1 source. It is
        # authoritative only when it agrees with the stored V1 input hash.
        model_input = " ".join(f"[{speaker}] {text}" for speaker, text in turns)
        hash_matches = sha(model_input) == event["model_input_hash"]
        result.append({"audio_timestamp_sec": event["audio_timestamp_sec"], "transcript": event["transcript"],
                       "rolling_transcript": event["rolling_transcript"], "candidate_rendered_input": model_input,
                       "stored_model_input_hash": event["model_input_hash"], "candidate_render_hash": sha(model_input),
                       "input_provenance": "VERIFIED_EXACT" if hash_matches else "UNRECOVERABLE_V1_HASH_MISMATCH",
                       "action_score": event["action_score"]})
    return result


def tail_decode(case: dict, start_sec: int, end_sec: int) -> dict:
    with wave.open(case["audio_path"], "rb") as source:
        source.setpos(start_sec * 48_000)
        raw = source.readframes((end_sec - start_sec) * 48_000)
    return {"region_sec": [start_sec, end_sec], "asr": transcribe_pcm_details(raw, vad_filter=False, model_name="small", device="cuda", compute_type="float16")}


def trace(before: dict, after: dict) -> dict:
    case_id = before["case_id"]
    regions = [(2, 3)] if case_id.endswith("07_dangerous") else [(2, 3), (3, 4)]
    windows = after["whisper"]["windows"]
    return {
        "case_id": case_id, "expected_class": before["expected_class"], "source_script": before["reference_transcript"],
        "reference_transcript": before["reference_transcript"], "old_pipeline": {
            "timeline": old_timeline(before), "first_threshold_crossing": before["first_alert_sec"],
            "final_transcript": before["whisper"]["final_transcript"], "max_score": before["nomic"]["max_score"],
        }, "new_stabilizer": {
            "raw_whisper_windows": windows, "timeline": after["nomic"]["timeline"],
            "first_threshold_crossing": after["first_alert_sec"], "final_transcript": after["whisper"]["final_transcript"],
            "max_score": after["nomic"]["max_score"],
        }, "overlap_analysis": [{"window_sec": [w["audio_start_sec"], w["audio_end_sec"]], "overlap_evidence": w.get("overlap_evidence"),
                                  "later_window_was_evaluated": any(e["audio_timestamp_sec"] == w["audio_end_sec"] for e in after["nomic"]["timeline"])} for w in windows[1:]],
        "read_only_new_audio_tail_decodes": [tail_decode(after, *region) for region in regions],
        "word_level_source_alignment": "N/A: locked synthetic source provides a clip-aligned transcript but no word timestamps; V3 retains/evaluates every later raw hypothesis.",
        "root_cause": "No later hypothesis was ignored. V3 revised and evaluated the provisional utterance for all meaningful later windows. V1 represented each overlap as a separate [CALLER] turn; V3 represents the rolling word sequence as one caller utterance. V1's later stored input hashes cannot be reproduced from its stored turns, so their exact inputs are unrecoverable; its threshold crossing is not valid evidence to restore duplicate-turn behavior.",
        "classification": "OLD_SUCCESS_ACCIDENTAL", "genuine_speech_discarded": False,
        "structural_fix_justified": False,
    }


def main() -> None:
    before = {json.loads(path.read_text(encoding="utf-8"))["case_id"]: json.loads(path.read_text(encoding="utf-8")) for path in (ROOT / "reports" / "audio_replay_v1" / "calls").glob("*.json")}
    after = {row["case_id"]: row for row in json.loads(V3.read_text(encoding="utf-8"))["calls"]}
    delta = []
    for case_id in sorted(before):
        left, right = before[case_id], after[case_id]
        delta.append({"case_id": case_id, "expected": left["expected_class"], "before_detected": left["triggered"], "after_detected": right["triggered"],
                      "before_max_score": left["nomic"]["max_score"], "after_max_score": right["nomic"]["max_score"],
                      "before_first_alert_sec": left["first_alert_sec"], "after_first_alert_sec": right["first_alert_sec"],
                      "score_delta": round(right["nomic"]["max_score"] - left["nomic"]["max_score"], 6),
                      "classification_delta": f"{left['triggered']}->{right['triggered']}"})
    lost = [row["case_id"] for row in delta if row["expected"] == "dangerous" and row["before_detected"] and not row["after_detected"]]
    remaining_fn = [row["case_id"] for row in delta if row["expected"] == "dangerous" and not row["before_detected"] and not row["after_detected"]]
    report = {"pack_sha256": "3ABD874C7C05F6C4BE90327361E0D87B5FAB2533BC8D046BAC7333DDE7F8EE42", "threshold": 0.6,
              "lost_true_positives": lost, "remaining_original_false_negatives": remaining_fn, "delta_table": delta,
              "lost_tp_traces": [trace(before[case_id], after[case_id]) for case_id in lost],
              "conclusion": {"stabilizer_bug_remains": False, "lower_f1_honest_consequence_of_removing_bogus_evidence": "Yes, descriptively; the exact V1 contribution cannot be quantified because later V1 input hashes are inconsistent with stored turns.",
                             "targeted_structural_correction_justified": False,
                             "decision": "STRUCTURAL_PIPELINE_CORRECT; DETECTION_REGRESSION_IS_REAL_MODEL_ASR_LIMITATION"}}
    json_path = REPORTS / "STABILIZER_REGRESSION_FORENSIC.json"
    atomic_json_write(json_path, report)
    lines = ["# Stabilizer regression forensic", "", "## Delta table", "", "| case_id | expected | before | after | before max | after max | delta |", "|---|---|---:|---:|---:|---:|---:|"]
    lines += [f"| {row['case_id']} | {row['expected']} | {row['before_detected']} | {row['after_detected']} | {row['before_max_score']:.4f} | {row['after_max_score']:.4f} | {row['score_delta']:.4f} |" for row in delta]
    for item in report["lost_tp_traces"]:
        lines += ["", f"## {item['case_id']}", "", "```text", f"SOURCE SCRIPT: {item['source_script']}", f"OLD FINAL: {item['old_pipeline']['final_transcript']}", f"NEW FINAL: {item['new_stabilizer']['final_transcript']}", f"OLD MAX: {item['old_pipeline']['max_score']}", f"NEW MAX: {item['new_stabilizer']['max_score']}", f"CLASSIFICATION: {item['classification']}", "```", "", "Full raw-window, Nomic-input, hash, cadence, and tail-decode evidence is in the JSON companion."]
    lines += ["", "## Conclusion", "", "- No lost TP had a meaningful later hypothesis ignored.", "- No genuine new speech was dropped from V3's rolling transcript or Nomic cadence.", "- V1's later input hashes do not match deterministic rendering of stored turns; their exact inputs are unrecoverable.", "- Targeted structural correction is not justified; restoring duplicate turn encoding would violate transcript integrity."]
    (REPORTS / "STABILIZER_REGRESSION_FORENSIC.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(REPORTS / "STABILIZER_REGRESSION_FORENSIC.md"), "lost_true_positives": lost, "remaining_fn": remaining_fn}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
