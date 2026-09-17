from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from backend.semantic_benchmark import run_benchmark
from backend.semantic_dataset import base_cases, jury_red_team_cases

report=run_benchmark(base_cases(), jury_red_team_cases())
root=ROOT; out=root/"reports"; out.mkdir(exist_ok=True)
(out/"scut_semantic_benchmark.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
lines=["# SCUT Semantic Benchmark", "", "```json", json.dumps(report,indent=2,ensure_ascii=False), "```"]
(out/"scut_semantic_benchmark.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
print(json.dumps(report,ensure_ascii=False))
