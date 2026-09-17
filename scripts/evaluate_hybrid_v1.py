"""DEVELOPMENT_ONLY comparison of frozen v3 TRAIN OOF, Rules V2, and Hybrid V1."""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

def counts(pred, truth):
    tp=sum(p and y for p,y in zip(pred,truth)); fp=sum(p and not y for p,y in zip(pred,truth)); fn=sum(not p and y for p,y in zip(pred,truth)); tn=len(truth)-tp-fp-fn
    precision=tp/(tp+fp) if tp+fp else 0.; recall=tp/(tp+fn) if tp+fn else 0.; return {"tp":tp,"fp":fp,"fn":fn,"tn":tn,"precision":precision,"recall":recall,"f1":2*precision*recall/(precision+recall) if precision+recall else 0.}
def bucket(rows, pred, truth, selector):
    result={}
    for value in sorted({selector(r) for r in rows}):
        idx=[i for i,r in enumerate(rows) if selector(r)==value]; result[value]=counts([pred[i] for i in idx],[truth[i] for i in idx])
    return result
def main():
    from backend.hybrid_v1 import HybridBrainV1, NomicSignal
    from backend.realtime_pipeline import Utterance
    from scripts.championship_common import load_train_records
    from scripts.tail_aware_encoder import dangerous_action_target
    report=ROOT/"reports"/"scut_brain_championship_v3_pc5070"; output=ROOT/"output"/"scut_brain_championship_v2_pc5070"
    config=json.loads((report/"resolved_frozen_configuration.json").read_text(encoding="utf-8")); experiment=json.loads((report/"experiment_nonlinear_head__bf16_precisionfix__seed_17.json").read_text(encoding="utf-8"))
    train,_,_=load_train_records(ROOT); by_id={r["id"]:r for r in train}; protocol=json.loads((report.parent/"scut_brain_championship_v2_pc5070"/"championship_protocol.json").read_text(encoding="utf-8"))
    paths=[Path(value) for value in experiment["oof_files"]]
    oof={key:np.concatenate([np.load(path,allow_pickle=False)[key] for path in paths]) for key in np.load(paths[0],allow_pickle=False).files}
    rows=[by_id[str(i)] for i in oof["record_ids"]]; scores=oof["action_probabilities"].reshape(-1).tolist(); threshold=float(experiment["selected_threshold"]); truth=[bool(dangerous_action_target(r)) for r in rows]; nomic=[x>=threshold for x in scores]; rules=[]; hybrid=[]; recovered=Counter()
    for row,score,nomic_pred in zip(rows,scores,nomic):
        brain=HybridBrainV1(); decision=None
        for n,(speaker,text) in enumerate(row["turns"],1): decision=brain.ingest(Utterance(str(n),str(speaker).upper(),str(text),0,0),NomicSignal(float(score),source="V3_TRAIN_OOF"))
        rule_pred=decision["risk_level"] in {"HIGH_RISK","CRITICAL"}; hybrid_pred=rule_pred; rules.append(rule_pred); hybrid.append(hybrid_pred)
        if (not nomic_pred) and truth[len(rules)-1] and hybrid_pred:
            for family in decision["scam_families"] or ["UNSPECIFIED"]: recovered[family]+=1
    scope=lambda r: "asr" if r["id"].endswith("-asr-v1") else "clean"
    language=lambda r: "mixed" if str(r.get("language","")).startswith("mixed") else str(r.get("language","unknown"))
    result={"metric_scope":"DEVELOPMENT_ONLY_TRAIN_OOF","base":"NOMIC_TOP4_SMALL_NONLINEAR_HEAD","nomic_threshold":threshold,"records":len(rows),"nomic_alone":counts(nomic,truth),"evidence_rules_v2":counts(rules,truth),"hybrid_v1":counts(hybrid,truth),"per_language":{"nomic":bucket(rows,nomic,truth,language),"rules":bucket(rows,rules,truth,language),"hybrid":bucket(rows,hybrid,truth,language)},"clean_vs_asr":{"nomic":bucket(rows,nomic,truth,scope),"rules":bucket(rows,rules,truth,scope),"hybrid":bucket(rows,hybrid,truth,scope)},"protective_fp":{"nomic":sum(p and r["kind"]=="protective" for p,r in zip(nomic,rows)),"rules":sum(p and r["kind"]=="protective" for p,r in zip(rules,rows)),"hybrid":sum(p and r["kind"]=="protective" for p,r in zip(hybrid,rows))},"legitimate_fp":{"nomic":sum(p and r["kind"]=="legitimate" for p,r in zip(nomic,rows)),"rules":sum(p and r["kind"]=="legitimate" for p,r in zip(rules,rows)),"hybrid":sum(p and r["kind"]=="legitimate" for p,r in zip(hybrid,rows))},"manipulation_only_fp":{"nomic":sum(p and not dangerous_action_target(r) and r["kind"]=="dangerous" for p,r in zip(nomic,rows)),"rules":sum(p and not dangerous_action_target(r) and r["kind"]=="dangerous" for p,r in zip(rules,rows)),"hybrid":sum(p and not dangerous_action_target(r) and r["kind"]=="dangerous" for p,r in zip(hybrid,rows))},"NOMIC_FALSE_NEGATIVES_RECOVERED_BY_RULES":sum((not n) and y and h for n,y,h in zip(nomic,truth,hybrid)),"recovered_general_evidence_families":dict(sorted(recovered.items())),"NOMIC_FALSE_POSITIVES_SUPPRESSED_BY_PROTECTIVE_LOGIC":sum(n and not h and r["kind"]=="protective" for n,h,r in zip(nomic,hybrid,rows)),"NEW_FALSE_POSITIVES_INTRODUCED_BY_RULES":sum((not n) and h and not y for n,h,y in zip(nomic,hybrid,truth)),"DANGEROUS_CASES_LOST_VS_NOMIC":sum(n and not h and y for n,h,y in zip(nomic,hybrid,truth)),"rule_design":"Frozen before this evaluation; no OOF texts are written to this output."}
    destination=ROOT/"reports"/"hybrid_v1"/"development_comparison.json"; destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
