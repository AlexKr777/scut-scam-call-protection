"""Local development-machine benchmark; Whisper and TUF are explicitly excluded."""
from __future__ import annotations
import json, statistics, time, tracemalloc, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
def quantile(values, q): return sorted(values)[min(len(values)-1, int((len(values)-1)*q))]
def sample(fn, count):
    for _ in range(3): fn()
    values=[]
    for _ in range(count): started=time.perf_counter(); fn(); values.append((time.perf_counter()-started)*1000)
    return {"samples":count,"p50_ms":statistics.median(values),"p95_ms":quantile(values,.95)}
def main():
    import torch
    from backend.hybrid_v1 import EvidenceRulesV2, HybridBrainV1, NomicSignal
    from backend.nomic_deployment_v1 import NomicDeploymentV1
    from backend.realtime_pipeline import CALLER, Utterance
    text="Bank security: please read the six digits from the SMS and stay on the line."
    turn=Utterance("bench",CALLER,text,0,0); rules=EvidenceRulesV2(); runtime=NomicDeploymentV1(); state=HybridBrainV1().state
    def rule_call(): rules.analyze(turn,state)
    tracemalloc.start(); rule_metrics=sample(rule_call,200); _,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
    torch.cuda.reset_peak_memory_stats(); nomic_metrics=sample(lambda: runtime.score([(CALLER,text)]),20); vram=int(torch.cuda.max_memory_allocated())
    signal=runtime.score([(CALLER,text)])
    def engine_call():
        brain=HybridBrainV1(); brain.state.ingest(brain.rules.analyze(turn,brain.state)); brain.risk.decide(brain.state,signal)
    engine_metrics=sample(engine_call,500)
    def hybrid_call(): HybridBrainV1().ingest(turn,runtime.score([(CALLER,text)]))
    hybrid_metrics=sample(hybrid_call,20)
    result={"scope":"CURRENT_RTX_5070_DEVELOPMENT_MACHINE_EXCLUDING_WHISPER","nomic_gpu":nomic_metrics|{"peak_vram_bytes":vram},"evidence_rules_cpu":rule_metrics|{"peak_python_tracemalloc_bytes":peak},"risk_engine_cpu":engine_metrics,"hybrid_end_to_end_excluding_whisper":hybrid_metrics,"tuf_laptop_benchmark":"NOT_RUN_REQUIRED_BEFORE_DEMO"}
    path=ROOT/"reports"/"hybrid_v1"/"performance.json"; path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,indent=2))
if __name__=="__main__": main()
