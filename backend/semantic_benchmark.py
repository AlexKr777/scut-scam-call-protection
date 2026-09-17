"""Offline reproducible benchmark for the local semantic path."""
from __future__ import annotations
import statistics, time
from .realtime_pipeline import Utterance
from .semantic_dataset import SemanticCase
from .semantic_risk import SemanticRiskEngine

def _evaluate(cases: list[SemanticCase]) -> tuple[list[dict], list[float]]:
    rows=[]; times=[]
    for case in cases:
        engine=SemanticRiskEngine(); started=time.perf_counter(); event=None
        for number,(speaker,text) in enumerate(case.turns): event=engine.ingest(Utterance(f"{case.id}-{number}",speaker,text,number,number+1))
        elapsed=(time.perf_counter()-started)*1000; times.append(elapsed)
        rows.append({"id":case.id,"language":case.language,"expected":case.expected,"actual":event.level,"pass":case.expected==event.level,"kind":case.kind})
    return rows,times

def _rate(rows: list[dict], expected: str, actual: str="CRITICAL") -> float:
    subset=[row for row in rows if row["expected"]==expected]
    return round(sum(row["actual"]==actual for row in subset)/len(subset)*100,2) if subset else 0.0

def run_benchmark(cases: list[SemanticCase], jury: list[SemanticCase]) -> dict:
    rows, times=_evaluate(cases); jury_rows,jury_times=_evaluate(jury); all_rows=rows+jury_rows
    languages={language: round(sum(row["pass"] for row in all_rows if row["language"]==language)/max(1,sum(row["language"]==language for row in all_rows))*100,2) for language in ("ru","ro","en")}
    return {"runtime":"python-local-deterministic","model":"typed multilingual heuristic baseline","datasetVersion":"2026-09-07.1","ontologyVersion":"2026-09-07.1","caseCount":len(rows),"juryHoldoutCount":len(jury_rows),"criticalScamRecall":_rate(rows,"CRITICAL"),"dangerousActionRecall":_rate(rows,"CRITICAL"),"protectiveFalseCriticalRate":round(100-_rate([r for r in rows if r["kind"]=="safe"],"SAFE", "SAFE"),2),"legitimateFalseCriticalRate":round(sum(r["actual"]=="CRITICAL" for r in rows if r["kind"]=="safe")/max(1,sum(r["kind"]=="safe" for r in rows))*100,2),"juryRedTeamRecall":_rate(jury_rows,"CRITICAL"),"languages":languages,"latencyMs":{"p50":round(statistics.median(times),3),"p95":round(sorted(times)[max(0, int(len(times)*.95)-1)],3),"max":round(max(times),3)},"failingExamples":[r for r in all_rows if not r["pass"]],"readiness":"LOCAL_SEMANTIC_FUNCTIONAL_BUT_QUALITY_GATE_NOT_MET"}
