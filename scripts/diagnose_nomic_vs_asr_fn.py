"""Diagnostic-only clean-text versus stabilized-ASR scoring with NOMIC_DEPLOYMENT_V1."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.audio_replay import atomic_json_write
from backend.nomic_deployment_v1 import NomicDeploymentV1
from scripts.tail_aware_encoder import pack_turns

LOCK = ROOT / "data" / "audio_replay_v1" / "audio_replay_v1_manifest.lock.json"
V3 = ROOT / "reports" / "audio_replay_v1_stabilizer_v3" / "SCUT_AUDIO_REPLAY_V1_STABILIZER_V3_RESULTS.json"
OUT = ROOT / "reports" / "audio_replay_v1_stabilizer_v3"
THRESHOLD = 0.6


def evaluate(runtime: NomicDeploymentV1, text: str) -> dict:
    turns = [("CALLER", text)]
    packed = pack_turns(turns, runtime.adapter.tokenizer, 384)
    signal = runtime.score(turns)
    return {"input": packed, "token_count": len(runtime.adapter.tokenizer(packed, add_special_tokens=True)["input_ids"]),
            "input_hash": hashlib.sha256(packed.encode("utf-8")).hexdigest().upper(), "action_score": signal.action_score,
            "margin": signal.action_score - THRESHOLD, "dangerous": signal.action_score >= THRESHOLD,
            "threshold": THRESHOLD}


def verdict(clean: dict, asr: dict, streaming: dict) -> str:
    if clean["dangerous"] and asr["dangerous"] and not streaming["dangerous"]:
        return "PIPELINE_ANOMALY"
    if clean["dangerous"] and not asr["dangerous"]:
        return "BOTH" if clean["margin"] <= .10 else "ASR_CAUSED"
    if not clean["dangerous"] and not asr["dangerous"]:
        return "NOMIC_CAUSED"
    if clean["dangerous"] and asr["dangerous"] and streaming["dangerous"]:
        return "NOT_A_FALSE_NEGATIVE"
    return "MIXED_REVIEW"


def main() -> None:
    manifest = json.loads(LOCK.read_text(encoding="utf-8"))
    cases = {case["case_id"]: case for case in manifest["cases"] if case.get("case_id")}
    v3 = {case["case_id"]: case for case in json.loads(V3.read_text(encoding="utf-8"))["calls"]}
    selected = [case for case in cases.values() if case.get("strict_score_eligible") and case["expected_class"] == "dangerous"]
    runtime = NomicDeploymentV1()
    rows = []
    for source in sorted(selected, key=lambda item: item["case_id"]):
        actual = v3[source["case_id"]]
        timeline = actual["nomic"]["timeline"]
        maximum = max(timeline, key=lambda event: event["action_score"])
        streaming = {"all_inputs": timeline, "max_score": maximum["action_score"], "max_timestamp_sec": maximum["audio_timestamp_sec"],
                     "dangerous": maximum["action_score"] >= THRESHOLD, "margin": maximum["action_score"] - THRESHOLD}
        clean = evaluate(runtime, source["reference_transcript"])
        asr = evaluate(runtime, actual["whisper"]["final_transcript"])
        rows.append({"case_id": source["case_id"], "expected_class": source["expected_class"], "source_script": source["reference_transcript"],
                     "final_stabilized_whisper_transcript": actual["whisper"]["final_transcript"], "clean_text_control": clean,
                     "asr_text_control": asr, "streaming": streaming, "verdict": verdict(clean, asr, streaming)})
    fns = [row for row in rows if not row["streaming"]["dangerous"]]
    aggregate = {"strict_dangerous_cases": len(rows), "mean_clean_score": sum(row["clean_text_control"]["action_score"] for row in rows) / len(rows),
                 "mean_asr_score": sum(row["asr_text_control"]["action_score"] for row in rows) / len(rows),
                 "mean_score_delta": sum(row["asr_text_control"]["action_score"] - row["clean_text_control"]["action_score"] for row in rows) / len(rows),
                 "improved_by_asr": sum(row["asr_text_control"]["action_score"] > row["clean_text_control"]["action_score"] for row in rows),
                 "degraded_by_asr": sum(row["asr_text_control"]["action_score"] < row["clean_text_control"]["action_score"] for row in rows),
                 "crossing_clean_tp_to_asr_fn": sum(row["clean_text_control"]["dangerous"] and not row["asr_text_control"]["dangerous"] for row in rows),
                 "already_below_threshold_on_clean": sum(not row["clean_text_control"]["dangerous"] for row in rows)}
    report = {"diagnostic_only": True, "checkpoint_sha256": "4D436D29DCB76AFDF86538E336E4B22DF413F840274EF56856A72FCB30F19E20",
              "threshold": THRESHOLD, "pack_sha256": manifest["pack_sha256"], "cases": rows, "false_negatives": fns, "aggregate": aggregate}
    atomic_json_write(OUT / "NOMIC_VS_ASR_FN_DIAGNOSIS.json", report)
    md = ["# Nomic vs ASR false-negative diagnosis", "", "| Case | Clean score | ASR score | Stream max | Verdict |", "|---|---:|---:|---:|---|"]
    md += [f"| {row['case_id']} | {row['clean_text_control']['action_score']:.4f} | {row['asr_text_control']['action_score']:.4f} | {row['streaming']['max_score']:.4f} | {row['verdict']} |" for row in fns]
    md += ["", "Full exact inputs, hashes, token counts, source text, stabilized text, and every stored streaming evaluation are in the JSON companion.", "", "## Aggregate", "", "```json", json.dumps(aggregate, ensure_ascii=False, indent=2), "```"]
    (OUT / "NOMIC_VS_ASR_FN_DIAGNOSIS.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT / "NOMIC_VS_ASR_FN_DIAGNOSIS.json"), "markdown": str(OUT / "NOMIC_VS_ASR_FN_DIAGNOSIS.md"), "false_negatives": [{"case_id": row["case_id"], "verdict": row["verdict"], "clean": row["clean_text_control"]["action_score"], "asr": row["asr_text_control"]["action_score"], "stream": row["streaming"]["max_score"]} for row in fns]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
