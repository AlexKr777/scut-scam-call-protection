"""Apply the reviewed, dialogue-supported v3 kind corrections only."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "experiments" / "semantic_corpus_v3.json"
NUMBERS = {11, 13, 24, 30, 34, 38, 40, 43}
PREFIXES = ("ru", "ro", "en", "mix")


def main() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    wanted = {f"scut-v3-{prefix}-{number:03d}" for prefix in PREFIXES for number in NUMBERS}
    corrected = []
    for row in corpus["bases"]:
        if row["id"] in wanted:
            expected = {"ACTUAL_REQUEST", "DIRECTED_AT_USER"}
            if not expected <= set(row["labels"]) or row["kind"] != "legitimate":
                raise SystemExit(f"Unexpected reviewed record state: {row['id']}")
            row["kind"] = "dangerous"
            corrected.append(row["id"])
    if set(corrected) != wanted:
        raise SystemExit("Reviewed metadata-correction target set did not match corpus")
    CORPUS.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"corrected_kind_to_dangerous": corrected}, ensure_ascii=False))


if __name__ == "__main__":
    main()
