"""Validate the externally authored SCUT v3 corpus without generating bases."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "experiments" / "semantic_corpus_v3.json"
DEFAULT_REPORT = ROOT / "reports" / "scut_semantic_corpus_v3_validation_report.json"

ACTION_LABELS = {
    "CREDENTIAL_DISCLOSURE", "MONEY_OR_ASSET_MOVEMENT", "REMOTE_DEVICE_ACCESS",
    "AUTHORIZATION_OR_APPROVAL", "LINK_OR_QR_ACTION", "CASH_OR_COURIER_HANDOFF",
    "LOAN_OR_CREDIT_ACTION", "CRYPTO_OR_GIFT_VALUE_TRANSFER", "PERSONAL_DATA_DISCLOSURE",
}
MANIPULATION_LABELS = {
    "URGENCY_OR_TIME_PRESSURE", "FEAR_OR_THREAT", "AUTHORITY_PRESSURE", "SECRECY",
    "ISOLATION", "DISCOURAGE_VERIFICATION", "KEEP_CALL_ACTIVE",
    "EMOTIONAL_OR_FAMILY_PRESSURE", "TRUST_OR_COMPLIANCE_MANIPULATION",
}
PRAGMATIC_LABELS = {
    "DIRECTED_AT_USER", "ACTUAL_REQUEST", "INDIRECT_REQUEST", "PROTECTIVE_ADVICE",
    "NEGATION", "QUOTATION", "HYPOTHETICAL", "CURRENT_CONDITIONAL_DIRECTIVE",
    "CALLER_CONFIRMATION",
}
ALLOWED_LABELS = ACTION_LABELS | MANIPULATION_LABELS | PRAGMATIC_LABELS
LANGUAGES = {"ru", "ro", "en", "mixed-ru-ro", "mixed-ru-en", "mixed-ro-en"}
SPLITS = {"train", "validation", "test"}
KINDS = {"dangerous", "protective", "legitimate"}
SPEAKERS = {"CALLER", "USER"}


def normalized_text(row: dict[str, Any]) -> str:
    text = " ".join(turn[1] for turn in row["turns"])
    return re.sub(r"[^\w]+", "", text.casefold(), flags=re.UNICODE)


def token_set(row: dict[str, Any]) -> set[str]:
    text = " ".join(turn[1] for turn in row["turns"]).casefold()
    return {token for token in re.findall(r"\w+", text, flags=re.UNICODE) if len(token) > 2}


def add_error(errors: list[str], message: str) -> None:
    if message not in errors:
        errors.append(message)


def validate_row(row: Any, is_base: bool, errors: list[str]) -> None:
    name = row.get("id", "<missing-id>") if isinstance(row, dict) else "<non-object>"
    if not isinstance(row, dict):
        add_error(errors, f"{name}: row must be an object")
        return
    expected = {"id", "base_scenario_id", "split", "language", "turns", "labels"}
    expected |= {"kind", "minimal_pair_id", "adversarial"} if is_base else {"variant_type"}
    if set(row) != expected:
        add_error(errors, f"{name}: fields must be exactly {sorted(expected)}")
    for field in ("id", "base_scenario_id", "split", "language"):
        if not isinstance(row.get(field), str) or not row[field]:
            add_error(errors, f"{name}: {field} must be a non-empty string")
    if row.get("split") not in SPLITS:
        add_error(errors, f"{name}: unknown split {row.get('split')!r}")
    if row.get("language") not in LANGUAGES:
        add_error(errors, f"{name}: unknown language {row.get('language')!r}")
    turns = row.get("turns")
    if not isinstance(turns, list) or not turns:
        add_error(errors, f"{name}: turns must be a non-empty list")
    elif not all(isinstance(turn, list) and len(turn) == 2 and turn[0] in SPEAKERS and isinstance(turn[1], str) and turn[1].strip() for turn in turns):
        add_error(errors, f"{name}: each turn must be [CALLER|USER, non-empty text]")
    labels = row.get("labels")
    if not isinstance(labels, list) or not labels or not all(isinstance(label, str) for label in labels):
        add_error(errors, f"{name}: labels must be a non-empty list of strings")
    elif len(labels) != len(set(labels)):
        add_error(errors, f"{name}: labels contain duplicates")
    elif set(labels) - ALLOWED_LABELS:
        add_error(errors, f"{name}: unknown corpus labels {sorted(set(labels) - ALLOWED_LABELS)}")
    if is_base:
        if row.get("base_scenario_id") != row.get("id"):
            add_error(errors, f"{name}: base_scenario_id must equal id")
        if row.get("kind") not in KINDS:
            add_error(errors, f"{name}: unknown kind {row.get('kind')!r}")
        if row.get("minimal_pair_id") is not None and not isinstance(row.get("minimal_pair_id"), str):
            add_error(errors, f"{name}: minimal_pair_id must be string or null")
        if not isinstance(row.get("adversarial"), bool):
            add_error(errors, f"{name}: adversarial must be boolean")
    elif row.get("variant_type") != "asr_corrupted":
        add_error(errors, f"{name}: unsupported variant_type {row.get('variant_type')!r}")


def validate(corpus: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(corpus, dict) or set(corpus) != {"bases", "variants"}:
        return {"errors": ["top level must contain exactly bases and variants"]}
    bases, variants = corpus["bases"], corpus["variants"]
    if not isinstance(bases, list) or not isinstance(variants, list):
        return {"errors": ["bases and variants must be arrays"]}
    for row in bases:
        validate_row(row, True, errors)
    for row in variants:
        validate_row(row, False, errors)
    rows = bases + variants
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    for duplicate in sorted(key for key, count in Counter(ids).items() if count > 1):
        add_error(errors, f"duplicate id: {duplicate}")
    base_ids = [row.get("base_scenario_id") for row in bases if isinstance(row, dict)]
    for duplicate in sorted(key for key, count in Counter(base_ids).items() if count > 1):
        add_error(errors, f"duplicate base_scenario_id among bases: {duplicate}")
    base_map = {row.get("id"): row for row in bases if isinstance(row, dict)}
    for row in variants:
        if not isinstance(row, dict):
            continue
        source = base_map.get(row.get("base_scenario_id"))
        if source is None:
            add_error(errors, f"orphan variant: {row.get('id')}")
        elif any(row.get(field) != source.get(field) for field in ("split", "language", "labels")):
            add_error(errors, f"variant metadata differs from base: {row.get('id')}")
    exact: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("turns"), list):
            exact[normalized_text(row)].append(row.get("id", "<missing-id>"))
    duplicate_texts = [group for group in exact.values() if len(group) > 1]
    for group in duplicate_texts:
        add_error(errors, f"exact normalized duplicate dialogue: {', '.join(group)}")
    near_duplicates: list[list[str]] = []
    for index, left in enumerate(bases):
        if not isinstance(left, dict) or not isinstance(left.get("turns"), list):
            continue
        left_tokens = token_set(left)
        for right in bases[index + 1:]:
            if not isinstance(right, dict) or left.get("language") != right.get("language") or not isinstance(right.get("turns"), list):
                continue
            right_tokens = token_set(right)
            overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
            if overlap >= 0.92:
                pair = [left.get("id", "<missing-id>"), right.get("id", "<missing-id>")]
                near_duplicates.append(pair)
                add_error(errors, f"high-overlap same-language near duplicate: {pair[0]}, {pair[1]} ({overlap:.2f})")
    pair_splits: dict[str, set[str]] = defaultdict(set)
    for row in bases:
        if isinstance(row, dict) and row.get("minimal_pair_id"):
            pair_splits[row["minimal_pair_id"]].add(row.get("split"))
    for pair, splits in sorted(pair_splits.items()):
        if len(splits) > 1:
            add_error(errors, f"minimal-pair split leakage: {pair}")
    by_split = {split: [row for row in bases if isinstance(row, dict) and row.get("split") == split] for split in SPLITS}
    for split, group in by_split.items():
        languages = {row.get("language") for row in group}
        for language in ("ru", "ro", "en"):
            if language not in languages:
                add_error(errors, f"{split} missing {language} base")
        if not any(str(row.get("language")).startswith("mixed-") for row in group):
            add_error(errors, f"{split} missing mixed-language base")
        if not any(row.get("kind") == "protective" for row in group):
            add_error(errors, f"{split} missing protective base")
        if not any(row.get("kind") == "legitimate" for row in group):
            add_error(errors, f"{split} missing legitimate base")
        if not any(len(row.get("turns", [])) > 1 for row in group):
            add_error(errors, f"{split} missing multi-turn base")
    train_labels = {label for row in by_split["train"] for label in row.get("labels", [])}
    missing_train = sorted(ALLOWED_LABELS - train_labels)
    for label in missing_train:
        add_error(errors, f"train missing label coverage: {label}")
    # A live caller request paired with coercive manipulation is not legitimate.
    # This is a metadata-only coherence check; it does not infer a new ontology label.
    for row in bases:
        if not isinstance(row, dict):
            continue
        labels = set(row.get("labels", []))
        if row.get("kind") == "legitimate" and {"ACTUAL_REQUEST", "DIRECTED_AT_USER"} <= labels and labels & MANIPULATION_LABELS:
            add_error(errors, f"metadata kind contradicts active coercive caller request: {row.get('id')}")
    label_counts = Counter(label for row in bases if isinstance(row, dict) for label in row.get("labels", []))
    language_counts = Counter(row.get("language") for row in bases if isinstance(row, dict))
    kind_counts = Counter(row.get("kind") for row in bases if isinstance(row, dict))
    variant_language_counts = Counter(row.get("language") for row in variants if isinstance(row, dict))
    return {
        "base_count": len(bases), "variant_count": len(variants), "language_base_counts": dict(sorted(language_counts.items())),
        "variant_language_counts": dict(sorted(variant_language_counts.items())), "kind_base_counts": dict(sorted(kind_counts.items())),
        "split_base_counts": {split: len(by_split[split]) for split in sorted(SPLITS)}, "label_counts": dict(sorted(label_counts.items())),
        "multi_turn_bases": sum(len(row.get("turns", [])) > 1 for row in bases if isinstance(row, dict)),
        "caller_confirmation_bases": sum("CALLER_CONFIRMATION" in row.get("labels", []) for row in bases if isinstance(row, dict)),
        "adversarial_bases": sum(bool(row.get("adversarial")) for row in bases if isinstance(row, dict)),
        "minimal_pair_groups": len(pair_splits), "manipulation_only_bases": sum(bool(set(row.get("labels", [])) & MANIPULATION_LABELS) and not bool(set(row.get("labels", [])) & ACTION_LABELS) for row in bases if isinstance(row, dict)),
        "exact_duplicate_groups": duplicate_texts, "near_duplicate_pairs": near_duplicates,
        "errors": errors, "valid": not errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    try:
        corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Unable to read corpus: {error}", file=sys.stderr)
        return 2
    report = validate(corpus)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
