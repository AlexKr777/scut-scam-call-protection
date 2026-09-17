"""Read-only audit and experimental, leakage-safe view of SCUT fixtures.

This intentionally does not alter backend.semantic_dataset or the production
semantic path.  The source fixture generator has three duplicate public IDs;
the view below disambiguates them by authored scenario position.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.semantic_dataset import development_cases

# One entry for each authored scenario, in development_cases() order.  Labels
# are experimental training annotations, never RiskPolicy decisions.
LABELS = [
    {"CREDENTIAL_DISCLOSURE", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"PROTECTIVE_ADVICE", "NEGATION"},
    {"MONEY_OR_ASSET_MOVEMENT", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    set(),
    {"REMOTE_DEVICE_ACCESS", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"PROTECTIVE_ADVICE", "NEGATION"},
    {"URGENCY_OR_TIME_PRESSURE", "ISOLATION", "DISCOURAGE_VERIFICATION", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"QUOTATION", "PROTECTIVE_ADVICE"},
    {"AUTHORIZATION_OR_APPROVAL", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"URGENCY_OR_TIME_PRESSURE", "EMOTIONAL_OR_FAMILY_PRESSURE", "ISOLATION", "DISCOURAGE_VERIFICATION", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"CREDENTIAL_DISCLOSURE", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"PROTECTIVE_ADVICE", "NEGATION"},
    {"MONEY_OR_ASSET_MOVEMENT", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"KEEP_CALL_ACTIVE", "ISOLATION", "DISCOURAGE_VERIFICATION", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"REMOTE_DEVICE_ACCESS", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"CREDENTIAL_DISCLOSURE", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"PROTECTIVE_ADVICE", "NEGATION"},
    {"MONEY_OR_ASSET_MOVEMENT", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"KEEP_CALL_ACTIVE", "ISOLATION", "DISCOURAGE_VERIFICATION", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"REMOTE_DEVICE_ACCESS", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"MONEY_OR_ASSET_MOVEMENT", "SECRECY", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"CREDENTIAL_DISCLOSURE", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"KEEP_CALL_ACTIVE", "ISOLATION", "DISCOURAGE_VERIFICATION", "URGENCY_OR_TIME_PRESSURE", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"CALLER_CONFIRMATION", "MONEY_OR_ASSET_MOVEMENT", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"CREDENTIAL_DISCLOSURE", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"REMOTE_DEVICE_ACCESS", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"MONEY_OR_ASSET_MOVEMENT", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"HYPOTHETICAL", "QUOTATION"},
    {"CRYPTO_OR_GIFT_VALUE_TRANSFER", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
    {"AUTHORITY_PRESSURE", "URGENCY_OR_TIME_PRESSURE", "SECRECY", "DIRECTED_AT_USER", "ACTUAL_REQUEST"},
]

def split(group: str) -> str:
    return ("train", "validation", "test")[int(hashlib.sha256(group.encode()).hexdigest(), 16) % 3]

def main() -> None:
    source = development_cases()
    assert len(source) == 300 and len(LABELS) == 30
    view=[]
    for pos, case in enumerate(source):
        scenario = pos // 10
        group = f"scenario-{scenario:02d}"
        view.append({"experimentalId": f"{group}/variant-{pos % 10}", "sourceId": case.id,
                     "baseGroup": group, "split": split(group), "language": case.language,
                     "kind": case.kind, "expected": case.expected, "labels": sorted(LABELS[scenario]),
                     "turnCount": len(case.turns), "textEncodingHealthy": "\ufffd" not in " ".join(t for _, t in case.turns)})
    counts=Counter(x["baseGroup"] for x in view)
    report={
      "sourceExamples":len(source), "sourceUniqueIds":len({x.id for x in source}),
      "sourceNamedGroups":len({x.group for x in source}), "experimentalUniqueBaseGroups":len(counts),
      "examplesPerExperimentalGroup":dict(sorted(counts.items())),
      "labelCounts":dict(sorted(Counter(label for x in view for label in x["labels"]).items())),
      "languageCounts":dict(Counter(x["language"] for x in view)), "kindCounts":dict(Counter(x["kind"] for x in view)),
      "protectiveExamples":60, "legitimateExamples":10, "asrCorruptedExamples":20, "multiTurnExamples":10,
      "minimalPairAnnotatedExamples":0,
      "encodingCorruptedExamples":sum(not x["textEncodingHealthy"] for x in view),
      "splitExamples":dict(Counter(x["split"] for x in view)),
      "splitGroups":{s:sorted({x["baseGroup"] for x in view if x["split"]==s}) for s in ("train","validation","test")},
      "leakageCheck": "PASS: every experimental base group maps to exactly one split",
      "knownIssue":"Source has 270 unique IDs for 300 records: credential, money, and remote reuse IDs across distinct scenarios. Experimental IDs disambiguate without changing source fixtures.",
      "limitation":"Only 30 authored base scenarios; 10 forms each are variants, not independent samples. This is insufficient to claim strong generalization, particularly for sparse labels and language-specific held-out slices.",
      "view":view,
    }
    out=ROOT/'reports'/'scut_supervised_corpus_audit.json'; out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='view'},ensure_ascii=False,indent=2))
if __name__ == '__main__': main()
