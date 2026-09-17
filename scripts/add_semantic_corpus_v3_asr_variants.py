"""Add one realistic text-only ASR variant for each selected v3 base scenario."""
from __future__ import annotations

import json
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "experiments" / "semantic_corpus_v3.json"
SELECTIONS = {
    "ru": (1, 3, 5, 8, 10, 12, 15, 18, 21, 25, 32, 40),
    "ro": (2, 4, 6, 9, 11, 14, 17, 20, 24, 31, 39),
    "en": (1, 4, 7, 10, 13, 16, 19, 23, 28, 35, 42),
    "mix": (2, 5, 8, 11, 14, 18, 22, 27, 33, 38, 44),
}


def corrupt(text: str, language: str, seed: int) -> str:
    """Small, recoverable transcription errors; never alter semantic labels."""
    original = text
    text = text.replace("…", "").replace("—", " ")
    if seed % 5 == 0:
        text = text.replace(",", "").replace(".", "")
    elif seed % 5 == 1:
        text = text.replace("î", "i").replace("ă", "a").replace("ș", "s").replace("ț", "t")
    elif seed % 5 == 2:
        text = text.replace("official", "oficial").replace("support", "suport")
    elif seed % 5 == 3:
        text = text.replace(" SMS", " sms").replace("OTP", "otp")
    else:
        text = text.replace(" ", " ", 1).replace("?", "")
    if language.startswith("mixed"):
        text = text.replace(" okay", " ok").replace(" online", " on line")
    if text == original:
        text = text.replace(",", "").replace(".", "").replace("?", "")
    normalized = lambda value: re.sub(r"[^\w]+", "", value.casefold(), flags=re.UNICODE)
    if normalized(text) == normalized(original):
        # A short terminal deletion is a common, still-human-recoverable ASR
        # error and ensures variants are not normalization duplicates of bases.
        text = re.sub(r"\b(\w{5,})\b", lambda match: match.group(1)[:-1], text, count=1, flags=re.UNICODE)
    return " ".join(text.split())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true", help="replace an existing ASR-only variant set")
    args = parser.parse_args()
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    if corpus.get("variants") and not args.replace:
        raise SystemExit("Refusing to append ASR variants: corpus already has variants")
    if corpus.get("variants") and args.replace and any(row.get("variant_type") != "asr_corrupted" for row in corpus["variants"]):
        raise SystemExit("Refusing to replace non-ASR variants")
    bases = {row["id"]: row for row in corpus["bases"]}
    variants = []
    for prefix, numbers in SELECTIONS.items():
        for number in numbers:
            base_id = f"scut-v3-{prefix}-{number:03d}"
            base = bases.get(base_id)
            if base is None:
                raise SystemExit(f"Missing selected base: {base_id}")
            turns = [[speaker, corrupt(text, base["language"], number)] for speaker, text in base["turns"]]
            if turns == base["turns"]:
                raise SystemExit(f"No ASR text change made for {base_id}")
            variants.append({
                "id": f"{base_id}-asr-v1", "base_scenario_id": base_id, "split": base["split"],
                "language": base["language"], "turns": turns, "labels": base["labels"],
                "variant_type": "asr_corrupted",
            })
    if len(variants) != 45 or len({row["base_scenario_id"] for row in variants}) != 45:
        raise SystemExit("ASR selection must contain exactly 45 distinct base scenarios")
    corpus["variants"] = variants
    CORPUS.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added {len(variants)} ASR-corrupted text variants.")


if __name__ == "__main__":
    main()
