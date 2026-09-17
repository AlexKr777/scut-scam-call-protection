"""Build DEVELOPMENT_ONLY Hybrid V1 forensic taxonomy and integrity report.

Only the permitted v3 forensic summary and source code are read; no corpus
dialogue, observed validation, historical TEST, or fresh benchmark is opened.
"""
from __future__ import annotations
import hashlib, json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "reports" / "scut_brain_championship_v3_pc5070"
OUT = ROOT / "reports" / "hybrid_v1"

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def categories(records: list[dict], kind: str) -> dict:
    counts = Counter()
    by_language = Counter()
    for row in records:
        labels = set(row.get("gold_labels", [])); by_language[row.get("language", "unknown")] += 1
        if kind == "fn":
            for label, category in (("CREDENTIAL_DISCLOSURE", "credential_extraction"), ("MONEY_OR_ASSET_MOVEMENT", "money_movement"), ("CASH_OR_COURIER_HANDOFF", "cash_courier"), ("CRYPTO_OR_GIFT_VALUE_TRANSFER", "crypto_or_gift_value"), ("REMOTE_DEVICE_ACCESS", "remote_or_link"), ("PERSONAL_DATA_DISCLOSURE", "personal_data"), ("AUTHORIZATION_OR_APPROVAL", "authorization_approval")):
                if label in labels: counts[category] += 1
            if "URGENCY_OR_TIME_PRESSURE" in labels: counts["urgency"] += 1
            if "AUTHORITY_PRESSURE" in labels: counts["authority"] += 1
        else:
            for label, category in (("PROTECTIVE_ADVICE", "protective_advice"), ("NEGATION", "negation"), ("QUOTATION", "quotation"), ("HYPOTHETICAL", "hypothetical")):
                if label in labels: counts[category] += 1
    return {"count": len(records), "category_counts": dict(sorted(counts.items())), "language_counts": dict(sorted(by_language.items())), "method": "label-level aggregate only; no failed transcript text was copied"}

def main() -> None:
    forensic_path = V3 / "nomic_v2_forensic.json"
    forensic = json.loads(forensic_path.read_text(encoding="utf-8"))
    taxonomy = {"schema": 1, "metric_scope": "DEVELOPMENT_ONLY_TRAIN_OOF", "base_model": "NOMIC_TOP4_SMALL_NONLINEAR_HEAD", "championship_v3_result": "NO_QUALIFIED_CHAMPION", "dangerous_false_negatives": categories(forensic["dangerous_false_negatives"], "fn"), "relevant_safe_false_positives": categories(forensic["legitimate_false_positives"], "fp"), "rule_design_constraint": "Aggregate failure categories only; no exact-string OOF memorization."}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "nomic_weakness_taxonomy.json").write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    comparison = json.loads((OUT / "development_comparison.json").read_text(encoding="utf-8"))
    performance = json.loads((OUT / "performance.json").read_text(encoding="utf-8"))
    deployment = json.loads((ROOT / "output" / "hybrid_v1" / "NOMIC_DEPLOYMENT_V1" / "metadata.json").read_text(encoding="utf-8"))
    files = [ROOT / "backend" / "hybrid_v1.py", ROOT / "backend" / "hybrid_explanations.py", ROOT / "backend" / "nomic_deployment_v1.py", ROOT / "backend" / "services.py", ROOT / "tests" / "test_hybrid_v1.py", ROOT / "tests" / "test_hybrid_v1_adversarial.py", ROOT / "tests" / "test_hybrid_explanations.py"]
    report = ["# SCUT Hybrid Brain V1", "", "## Status", "", "SCUT_HYBRID_V1_NOT_READY", "", "This is an engineering checkpoint, not a championship result. Every comparison below is DEVELOPMENT_ONLY.", "", "## Integrity", "", "- Championship v3 remains `NO_QUALIFIED_CHAMPION`; v3 and RULES_V1 were not modified.", "- Historical TEST, observed validation, and the future fresh benchmark were not opened, created, or used.", "- No OOF transcript text is emitted. The final selected-model OOF comparison ran after rule finalization; no rule was patched against it.", "", "## Nomic deployment", "", f"- NOMIC_DEPLOYMENT_V1 checkpoint SHA-256: `{deployment['checkpoint_sha256']}`", "- top-4 nonlinear head; revision 1066b6599d099fbb93dfcb64f9c37a7c9e503e85; 384 tokens; BF16; TRAIN-only; seed 17.", "- NOT_CHAMPIONSHIP_CHAMPION=true; UNSEEN_VALIDATION_NOT_YET_RUN=true.", "", "## Development comparison", "", f"- Nomic: {comparison['nomic_alone']}", f"- Rules V2: {comparison['evidence_rules_v2']}", f"- Hybrid: {comparison['hybrid_v1']}", f"- Nomic FNs recovered: {comparison['NOMIC_FALSE_NEGATIVES_RECOVERED_BY_RULES']} ({comparison['recovered_general_evidence_families']})", f"- New false positives: {comparison['NEW_FALSE_POSITIVES_INTRODUCED_BY_RULES']}; lost Nomic dangerous cases: {comparison['DANGEROUS_CASES_LOST_VS_NOMIC']}; protective FPs suppressed: {comparison['NOMIC_FALSE_POSITIVES_SUPPRESSED_BY_PROTECTIVE_LOGIC']}.", "", "## Jury, explanation, and performance", "", "- 32 authored DEVELOPMENT_ONLY multilingual adversarial scenarios pass, including caller/user attribution and disclaimer contradictions.", "- Reason-code templates are deterministic in RU/RO/EN.", f"- Nomic GPU p50/p95: {performance['nomic_gpu']['p50_ms']:.2f}/{performance['nomic_gpu']['p95_ms']:.2f} ms; VRAM {performance['nomic_gpu']['peak_vram_bytes']} bytes.", f"- Rules CPU p50/p95: {performance['evidence_rules_cpu']['p50_ms']:.3f}/{performance['evidence_rules_cpu']['p95_ms']:.3f} ms.", "- TUF laptop benchmarking remains required.", "", "## Why V1 is not frozen", "", "- The fixed evidence-gated policy materially harms DEVELOPMENT_ONLY OOF action-alert performance: 89 dangerous Nomic detections are not severe alerts and 30 new false positives are introduced.", "- This fails the acceptance requirement to improve Nomic without unacceptable new false positives. No `hybrid_v1_manifest.json` was created.", "", "## Behavior-file hashes", ""]
    report.extend(f"- `{path.relative_to(ROOT)}`: `{digest(path)}`" for path in files)
    (OUT / "HYBRID_V1_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"status": "SCUT_HYBRID_V1_NOT_READY", "taxonomy": str(OUT / "nomic_weakness_taxonomy.json")}, ensure_ascii=False))

if __name__ == "__main__": main()
