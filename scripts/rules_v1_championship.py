"""Freeze and evaluate RULES_V1 on precommitted TRAIN OOF partitions only."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any
import numpy as np
from scripts.championship_common import atomic_json_write
from scripts.championship_metrics import select_action_threshold, select_thresholds, semantic_metrics, safety_qualification
from scripts.championship_reporting import build_oof_breakdowns
from scripts.rules_v1 import VERSION, WEIGHTS, FAMILIES, analyze

LABEL_MAP={"ACTUAL_REQUEST":"actual_request","DIRECTED_AT_USER":"directed_at_user","CREDENTIAL_DISCLOSURE":"credentials_request","MONEY_OR_ASSET_MOVEMENT":"money_request","REMOTE_DEVICE_ACCESS":"remote_access_request","LINK_OR_QR_ACTION":"link_or_qr_request","PERSONAL_DATA_DISCLOSURE":"personal_data_request","AUTHORITY_PRESSURE":"authority_pressure","URGENCY_OR_TIME_PRESSURE":"urgency","FEAR_OR_THREAT":"fear_or_threat","SECRECY":"secrecy","KEEP_CALL_ACTIVE":"keep_call_active","DISCOURAGE_VERIFICATION":"discourage_verification","PROTECTIVE_ADVICE":"protective_advice","NEGATION":"negation","QUOTATION":"quotation","HYPOTHETICAL":"hypothetical"}

def sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def freeze(directory:Path)->dict[str,Any]:
    behavior=Path(__file__).with_name("rules_v1.py")
    manifest={"version":VERSION,"behavior_file_hashes":{behavior.name:sha(behavior)},"supported_languages":["ru","ro","en","mixed"],"rule_families":sorted(FAMILIES),"weights":WEIGHTS,"action_score_mapping":"actual caller-directed action=0.85; otherwise=0.0","development_suite":"tests/test_rules_v1.py","behavior_manifest_sha256":None}
    payload=json.dumps(manifest,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode();manifest["behavior_manifest_sha256"]=hashlib.sha256(payload).hexdigest().upper();atomic_json_write(directory/"rules_v1_manifest.json",manifest);return manifest

def evaluate(protocol:dict[str,Any], train:list[dict[str,Any]], labels:list[str], directory:Path)->dict[str,Any]:
    directory.mkdir(parents=True,exist_ok=True); rows=[]; probs=[]; targets=[]; sem=[]; sem_target=[]; reasons=[]
    for row in train:
        result=analyze(row["turns"]); rows.append(dict(row,fold=int(protocol["fold_assignments"][row["id"]])))
        probs.append(result["action_score"]); targets.append(bool(row.get("kind")=="dangerous" and "ACTUAL_REQUEST" in row.get("labels",[])))
        sem.append([1.0 if result.get(key,False) else 0.0 for key in (LABEL_MAP.get(label,"__never__") for label in labels)])
        sem_target.append([label in row["labels"] for label in labels]);reasons.append(result["reason_codes"])
    p=np.asarray(probs); y=np.asarray(targets); s=np.asarray(sem); sy=np.asarray(sem_target)
    threshold=select_action_threshold(p,y,rows); thresholds=select_thresholds(s,sy,labels); pred=p>=threshold["threshold"]; qualification=safety_qualification(pred,y,rows)
    breakdown=build_oof_breakdowns(action_probabilities=p,action_targets=y,semantic_probabilities=s,semantic_targets=sy,labels=labels,rows=rows,action_threshold=threshold["threshold"],semantic_thresholds=thresholds,important_labels=labels)
    arrays={"action_probabilities":p,"action_targets":y,"semantic_probabilities":s,"semantic_targets":sy,"record_ids":np.array([r["id"] for r in rows]),"group_ids":np.array([r["base_scenario_id"] for r in rows]),"fold":np.array([r["fold"] for r in rows]),"language":np.array([r.get("language","unknown") for r in rows]),"kind_metadata":np.array([r["kind"] for r in rows])}
    for fold in range(3): np.savez_compressed(directory/f"rules_v1-fold_{fold}.npz",**{k:v[np.asarray([r["fold"]==fold for r in rows])] for k,v in arrays.items()})
    report={"id":"RULES_V1","candidate":"RULES_V1","depth":None,"deterministic_repeat_consistency":True,"evaluation_partition_count":3,"thresholds":{"action":threshold["threshold"],"semantic":thresholds},"qualification":qualification,"semantic_micro_f1":semantic_metrics(s>=np.array([thresholds.get(x,thresholds['__global__']) for x in labels]),sy,labels)["micro"]["f1"],"semantic_macro_f1":semantic_metrics(s>=np.array([thresholds.get(x,thresholds['__global__']) for x in labels]),sy,labels)["macro"]["f1"],"oof_breakdowns":breakdown,"reason_distribution":{x:sum(x in r for r in reasons) for x in sorted({x for r in reasons for x in r})}}
    atomic_json_write(directory/"rules_v1_evaluation.json",report);return report
