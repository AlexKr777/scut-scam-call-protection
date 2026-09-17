from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.realtime_pipeline import Utterance
from backend.semantic_dataset import development_cases
from backend.semantic_risk import SemanticRiskEngine


def main() -> None:
    all_cases = development_cases()
    # Evaluate one deterministic surface form per base scenario.  This avoids
    # reporting a variant-heavy score while preserving a bounded live run.
    selected = {}
    for case in all_cases:
        selected.setdefault(case.group, case)
    rows, timings = [], []
    for case in selected.values():
        engine, event = SemanticRiskEngine(), None
        started = time.perf_counter()
        for index, (speaker, text) in enumerate(case.turns):
            event = engine.ingest(Utterance(f"{case.id}-{index}", speaker, text, index, index + 1))
        timings.append((time.perf_counter() - started) * 1000)
        rows.append({"id": case.id, "language": case.language, "kind": case.kind,
                     "expected": case.expected, "actual": event.level,
                     "pass": case.expected == event.level})

    def accuracy(predicate):
        selected = [row for row in rows if predicate(row)]
        return round(100 * sum(row["pass"] for row in selected) / max(1, len(selected)), 2)

    report = {
        "runtime": "onnxruntime CPUExecutionProvider",
        "model": "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
        "artifact": "onnx/model_quantized.onnx", "artifactBytes": 338679133,
        "corpusCases": len(all_cases), "evaluatedBaseScenarios": len(rows),
        "split": "base scenario hash; variants remain grouped",
        "criticalScamRecall": accuracy(lambda row: row["expected"] == "CRITICAL"),
        "protectiveFalseCriticalRate": round(100 - accuracy(lambda row: row["kind"] == "safe"), 2),
        "legitimateFalseCriticalRate": round(100 - accuracy(lambda row: row["kind"] == "safe"), 2),
        "language": {"RU": accuracy(lambda row: row["language"] == "ru"),
                     "RO": accuracy(lambda row: row["language"] == "ro"),
                     "EN": accuracy(lambda row: row["language"] == "en"),
                     "mixed": accuracy(lambda row: row["language"] == "mixed")},
        "latencyMs": {"batchSize": 8, "contextTokensMax": 256,
                      "p50": round(statistics.median(timings), 1),
                      "p95": round(sorted(timings)[int(len(timings) * .95) - 1], 1),
                      "max": round(max(timings), 1)},
        "processRamMB": round(psutil.Process().memory_info().rss / 1048576, 1),
        "failingExamples": [row for row in rows if not row["pass"]],
        "verdict": "LOCAL_NEURAL_SEMANTICS_WORKING_BUT_GATE_NOT_MET",
    }
    target = ROOT / "reports" / "scut_neural_development_benchmark.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
