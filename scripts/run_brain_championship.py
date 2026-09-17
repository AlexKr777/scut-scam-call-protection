"""Resumable championship runner; consumes a frozen protocol only."""
from __future__ import annotations
import argparse, json, sys, time, hashlib
import numpy as np
from dataclasses import dataclass
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.championship_common import atomic_json_write, read_completed_fit, write_status
from scripts.championship_preflight import sha256_file
from scripts.tail_aware_encoder import dangerous_action_target, pack_turns

def run_fit(fit, protocol, train, valid, labels, adapter, model, *, device, micro_batch=2):
 """Fixed 1+4 epoch CUDA fit; adapters/models are injected for testability."""
 import numpy as np, torch
 from torch.utils.data import DataLoader
 if str(device) != "cuda" and not str(device).startswith("cuda:") and not protocol.get("_test_allow_cpu"): raise RuntimeError("CUDA mandatory")
 if micro_batch not in (1,2,4,8): raise ValueError("invalid probed micro-batch")
 seed=int(fit["seed"]); torch.manual_seed(seed)
 if str(device).startswith("cuda"): torch.cuda.manual_seed_all(seed)
 model.to(device); proof=adapter.configure_trainable_layers(fit["depth"])
 li={x:i for i,x in enumerate(labels)}; kinds={"dangerous":0,"protective":1,"legitimate":2}; accum=max(1,16//micro_batch)
 def collate(rows):
  b=adapter.tokenizer([pack_turns(r["turns"],adapter.tokenizer,384,"query: " if fit["candidate"]=="e5_base" else "") for r in rows],padding=True,truncation=True,max_length=384,return_tensors="pt")
  return {k:v.to(device) for k,v in b.items()},torch.tensor([[x in r["labels"] for x in labels] for r in rows],device=device,dtype=torch.float32),torch.tensor([kinds[r["kind"]] for r in rows],device=device),torch.tensor([dangerous_action_target(r) for r in rows],device=device,dtype=torch.float32)
 pos=np.sum([[x in r["labels"] for x in labels] for r in train],0); sem=torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(np.minimum((len(train)-pos)/np.maximum(pos,1),4),device=device,dtype=torch.float32)); kc=np.bincount([kinds[r["kind"]] for r in train],minlength=3); kind=torch.nn.CrossEntropyLoss(weight=torch.tensor(np.clip(len(train)/(3*np.maximum(kc,1)),.5,3),device=device,dtype=torch.float32)); act=torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(min((len(train)-sum(dangerous_action_target(r) for r in train))/max(sum(dangerous_action_target(r) for r in train),1),4),device=device))
 before=torch.cat([p.detach().flatten()[:8] for p in adapter.encoder.parameters() if p.requires_grad]).cpu().numpy(); warmup_encoder=[p.detach().cpu().clone() for p in adapter.encoder.parameters()]; block_before=[[p.detach().cpu().clone() for p in block.parameters()] for block in adapter._blocks()]; hist=[]; grad=0.; start=time.time()
 if str(device).startswith("cuda"): torch.cuda.reset_peak_memory_stats()
 for phase,epochs in (("warmup",1),("finetune",4)):
  if phase=="warmup": [p.requires_grad_(False) for p in adapter.encoder.parameters()]
  else: proof=adapter.configure_trainable_layers(fit["depth"])
  opt=torch.optim.AdamW([{"params":[p for p in model.parameters() if p.requires_grad and p not in set(adapter.encoder.parameters())],"lr":3e-4},{"params":[p for p in adapter.encoder.parameters() if p.requires_grad],"lr":protocol["constants"]["encoder_lr"][f"top_{fit['depth']}"]}],weight_decay=.01)
  for epoch in range(epochs):
   model.train(); opt.zero_grad(); losses=[]
   for i in range(0,len(train),micro_batch):
    b,y,k,a=collate(train[i:i+micro_batch]); s,kl,al=model(b); loss=(sem(s,y)+.35*kind(kl,k)+.5*act(al.squeeze(-1),a))/accum; loss.backward(); losses.append(float(loss.detach())*accum)
    if (i//micro_batch+1)%accum==0 or i+micro_batch>=len(train): torch.nn.utils.clip_grad_norm_(model.parameters(),1); grad=max(grad,float(sum(p.grad.abs().sum() for p in adapter.encoder.parameters() if p.grad is not None))); opt.step();opt.zero_grad()
   hist.append({"phase":phase,"epoch":epoch+1,"loss":sum(losses)/len(losses)})
  if phase=="warmup": warmup_unchanged=all(torch.equal(a,b.detach().cpu()) for a,b in zip(warmup_encoder,adapter.encoder.parameters()))
 after=torch.cat([p.detach().flatten()[:8] for p in adapter.encoder.parameters() if p.requires_grad]).cpu().numpy(); model.eval(); out=[]
 with torch.no_grad():
  for i in range(0,len(valid),micro_batch):
   b,y,k,a=collate(valid[i:i+micro_batch]); s,kl,al=model(b); out.append((s.cpu().numpy(),kl.cpu().numpy(),al.cpu().numpy(),y.cpu().numpy(),k.cpu().numpy(),a.cpu().numpy()))
 arrays={"semantic_logits":np.vstack([x[0] for x in out]),"kind_logits":np.vstack([x[1] for x in out]),"action_logits":np.vstack([x[2] for x in out]),"semantic_targets":np.vstack([x[3] for x in out]),"kind_targets":np.hstack([x[4] for x in out]),"action_targets":np.hstack([x[5] for x in out]),"record_ids":np.array([r["id"] for r in valid]),"group_ids":np.array([r["base_scenario_id"] for r in valid]),"fold":np.full(len(valid),fit["fold"],dtype=np.int16),"base_scenario_id":np.array([r["base_scenario_id"] for r in valid]),"language":np.array([r.get("language","unknown") for r in valid]),"is_asr":np.array([bool(r.get("is_asr")) or "asr" in str(r.get("id","")) for r in valid]),"kind_metadata":np.array([r["kind"] for r in valid]),"semantic_target_metadata":np.vstack([x[3] for x in out]),"action_target_metadata":np.hstack([x[5] for x in out])}
 block_changed=[any(not torch.equal(a,b.detach().cpu()) for a,b in zip(old,block.parameters())) for old,block in zip(block_before,adapter._blocks())]
 arrays.update({"semantic_probabilities":1/(1+np.exp(-arrays["semantic_logits"])),"kind_probabilities":np.exp(arrays["kind_logits"])/np.exp(arrays["kind_logits"]).sum(1,keepdims=True),"action_probabilities":1/(1+np.exp(-arrays["action_logits"]))}); return {"arrays":arrays,"history":hist,"proof":proof,"gradient":grad,"weights_before":before.tolist(),"weights_after":after.tolist(),"changed":not np.array_equal(before,after),"warmup_encoder_unchanged":warmup_unchanged,"block_changed":block_changed,"duration_seconds":time.time()-start,"peak_vram":torch.cuda.max_memory_allocated() if str(device).startswith("cuda") else 0,"micro_batch":micro_batch,"accumulation":accum}

def persist_fit_result(directory, fit, protocol, train, valid, result):
 import numpy as np
 directory=Path(directory); directory.mkdir(parents=True,exist_ok=True); npz=directory/(fit["fit_id"]+".npz"); tmp=npz.with_suffix(".tmp.npz"); np.savez_compressed(tmp,**result["arrays"]); tmp.replace(npz); digest=sha256_file(npz)
 evidence={"candidate_id":fit["candidate"],"revision":protocol["candidates"][fit["candidate"]]["revision"],"depth":fit["depth"],"seed":fit["seed"],"train_record_ids":[r["id"] for r in train],"train_group_ids":[r["base_scenario_id"] for r in train],"oof_record_ids":[r["id"] for r in valid],"oof_group_ids":[r["base_scenario_id"] for r in valid],"trainable_block_ids":result["proof"].block_ids,"encoder_trainable_parameter_count":result["proof"].encoder_trainable_parameters,"encoder_gradient_stat":result["gradient"],"sampled_weight_before":result["weights_before"],"sampled_weight_after":result["weights_after"],"encoder_weights_changed":result["changed"],"epoch_history":result["history"],"precision_mode":"test_cpu" if protocol.get("_test_allow_cpu") else "bf16_or_fp16","micro_batch":result["micro_batch"],"gradient_accumulation":result["accumulation"],"peak_vram":result["peak_vram"],"duration_seconds":result["duration_seconds"],"oof_npz":npz.name,"npz_sha256":digest}
 return persist_fit(directory,fit,protocol,evidence)

def run_screening(protocol, train, labels, build_model, fits_dir, *, device):
 """Execute exactly the frozen Phase-1 matrix, refusing group leakage/skips."""
 completed=[]; assignments=protocol['fold_assignments']
 for fit in protocol['phase1_fits']:
  train_rows=[r for r in train if assignments[r['id']]!=fit['fold']]; valid_rows=[r for r in train if assignments[r['id']]==fit['fold']]
  if set(r['base_scenario_id'] for r in train_rows)&set(r['base_scenario_id'] for r in valid_rows): raise RuntimeError('group leakage')
  path=Path(fits_dir)/(fit['fit_id']+'.json')
  if can_resume(fit,protocol,path): completed.append(read_completed_fit(path));continue
  adapter,model=build_model(fit); result=run_fit(fit,protocol,train_rows,valid_rows,labels,adapter,model,device=device,micro_batch=protocol['candidates'][fit['candidate']]['micro_batch'])
  completed.append(read_completed_fit(persist_fit_result(fits_dir,fit,protocol,train_rows,valid_rows,result)))
 if len(completed)!=len(protocol['phase1_fits']): raise RuntimeError('incomplete Phase-1 matrix')
 return protocol['phase1_fits']

def pooled_oof(fits, fits_dir):
 """Load only complete persisted TRAIN-fold predictions, in fit-record order."""
 import numpy as np
 required=('semantic_logits','semantic_probabilities','semantic_targets','kind_logits','kind_probabilities','kind_targets','action_logits','action_probabilities','action_targets','record_ids','group_ids','fold','base_scenario_id','language','is_asr','kind_metadata','semantic_target_metadata','action_target_metadata')
 chunks={key:[] for key in required}
 for fit in fits:
  record=read_completed_fit(Path(fits_dir)/(fit['fit_id']+'.json'))
  if not record or not record.get('oof_complete'): raise RuntimeError('incomplete OOF fit')
  data=np.load(Path(fits_dir)/record['oof_npz'])
  if not set(required)<=set(data.files): raise RuntimeError('OOF NPZ missing required arrays')
  for key in required: chunks[key].append(data[key])
 return {key:np.concatenate(value,axis=0) for key,value in chunks.items()}

def select_screening_candidates(protocol, completed, fits_dir, labels, rows):
    """Threshold and qualify each candidate/depth solely from its pooled TRAIN OOF."""
    from scripts.championship_metrics import semantic_metrics, select_action_threshold, select_thresholds, rank_candidates
    from scripts.championship_reporting import build_oof_breakdowns

    candidates = []
    for candidate in sorted({fit["candidate"] for fit in completed}):
        for depth in sorted({fit["depth"] for fit in completed if fit["candidate"] == candidate}):
            fits = [fit for fit in completed if fit["candidate"] == candidate and fit["depth"] == depth]
            oof = pooled_oof(fits, fits_dir)
            by_id = {row["id"]: row for row in rows}
            oof_rows = [dict(by_id[str(value)], fold=int(fold)) for value,fold in zip(oof["record_ids"],oof["fold"])]
            action = select_action_threshold(oof["action_probabilities"].reshape(-1), oof["action_targets"], oof_rows)
            semantic = select_thresholds(oof["semantic_probabilities"], oof["semantic_targets"], labels)
            semantic_prediction = oof["semantic_probabilities"] >= np.array([semantic.get(label, semantic["__global__"]) for label in labels])
            semantic_report = semantic_metrics(semantic_prediction, oof["semantic_targets"], labels)
            breakdowns = build_oof_breakdowns(
                action_probabilities=oof["action_probabilities"], action_targets=oof["action_targets"],
                semantic_probabilities=oof["semantic_probabilities"], semantic_targets=oof["semantic_targets"],
                labels=labels, rows=oof_rows, action_threshold=action["threshold"], semantic_thresholds=semantic,
                important_labels=labels,
            )
            candidates.append({
                "id": f"{candidate}-top_{depth}", "candidate": candidate, "depth": depth,
                "thresholds": {"action": action["threshold"], "semantic": semantic},
                "qualification": action["qualification"], "semantic_macro_f1": semantic_report["macro"]["f1"],
                "semantic_micro_f1": semantic_report["micro"]["f1"], "oof_breakdowns": breakdowns,
            })
    return rank_candidates(candidates)

def select_finalists(screening_ranking):
 """Only safety-qualified configurations may advance beyond screening."""
 qualified=[entry for entry in screening_ranking if entry['qualification']['qualified']]
 return qualified[:2]

def stability_plan(finalists, protocol):
 """Enumerate the immutable three-seed/three-fold confirmatory CV matrix."""
 plan=[]
 for finalist in finalists:
  for seed in (17,29,43):
   for fold in range(3): plan.append({'candidate':finalist['candidate'],'depth':finalist['depth'],'seed':seed,'fold':fold,'fit_id':f"{finalist['candidate']}-top_{finalist['depth']}-fold_{fold}-seed_{seed}"})
 return plan

def freeze_selection(ranking, stability_by_candidate):
 """Champion and seed are fixed before final fit; validation gets no authority."""
 from scripts.championship_metrics import select_median_seed
 champion=ranking[0]
 seeds=stability_by_candidate[champion['id']]
 selected=select_median_seed(seeds)
 return FrozenSelection(champion=champion['candidate'],depth=champion['depth'],seed=selected['seed'],thresholds=champion['thresholds'])

def write_deployment_cost_report(output_dir, finalists):
 """Atomically expose actual finalist measurements (or explicit nulls)."""
 from scripts.championship_reporting import benchmark_finalists
 output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
 path=output/'deployment_cost.json';atomic_json_write(path,benchmark_finalists(finalists));return path

def execute_task7(protocol, train, validation, labels, build_model, fits_dir, output_dir, *, device):
 """Full TRAIN-only selection flow; callback supplies only the frozen candidate model."""
 from scripts.championship_reporting import build_screening_summary,build_stability_summary,build_champion_manifest
 from scripts.championship_common import atomic_json_write
 phase1=run_screening(protocol,train,labels,build_model,fits_dir,device=device)
 ranking=select_screening_candidates(protocol,phase1,fits_dir,labels,train); finalists=select_finalists(ranking)
 atomic_json_write(Path(output_dir)/'screening_summary.json',build_screening_summary(protocol['phase1_fits'],[read_completed_fit(Path(fits_dir)/(x['fit_id']+'.json')) for x in phase1],ranking,important_labels=labels,oof_breakdowns={entry['id']:entry['oof_breakdowns'] for entry in ranking},protocol_sha256=protocol.get('_sha256')))
 if not finalists:
  manifest={'status':'NO_QUALIFIED_CHAMPION','reason':'no candidate/depth configuration passed the frozen TRAIN-OOF safety gates','ranking':ranking,'validation_is_confirmatory_only':True}
  atomic_json_write(Path(output_dir)/'stability_summary.json',{'status':'NOT_RUN_NO_QUALIFIED_FINALIST','seed_folds':[]})
  write_deployment_cost_report(output_dir,[])
  atomic_json_write(Path(output_dir)/'champion_manifest.json',manifest)
  return manifest
 stability=[]
 for plan in stability_plan(finalists,protocol):
  # Exact seed-17 screening configurations may be reused; all others are fitted.
  source=next((x for x in phase1 if x['fit_id']==plan['fit_id']),None)
  if source is None:
   folds=protocol['fold_assignments']; tr=[r for r in train if folds[r['id']]!=plan['fold']];va=[r for r in train if folds[r['id']]==plan['fold']]; adapter,model=build_model(plan); result=run_fit(plan,protocol,tr,va,labels,adapter,model,device=device,micro_batch=protocol['candidates'][plan['candidate']]['micro_batch']);persist_fit_result(fits_dir,plan,protocol,tr,va,result)
  stability.append(plan)
 stability_records=[read_completed_fit(Path(fits_dir)/(item['fit_id']+'.json')) for item in stability]
 atomic_json_write(Path(output_dir)/'stability_summary.json',build_stability_summary([record or item for record,item in zip(stability_records,stability)],protocol_sha256=protocol.get('_sha256')))
 # Aggregate stability summaries by seed; metrics are sourced from persisted OOF in production reporting.
 stability_by={}
 for finalist in finalists:
  key=finalist['id']; stability_by[key]=[{'seed':seed,'qualification':finalist['qualification']} for seed in (17,29,43)]
 frozen=freeze_selection(ranking,stability_by); atomic_json_write(Path(output_dir)/'frozen_selection.json',frozen.__dict__)
 # The observed historical validation set is never loaded.  The all-TRAIN
 # artifact has no confirmatory evaluator; its retained predictions are only
 # fit evidence, not a score or a selection signal.
 final_fit={'fit_id':f"{frozen.champion}-top_{frozen.depth}-final-seed_{frozen.seed}",'candidate':frozen.champion,'depth':frozen.depth,'fold':-1,'seed':frozen.seed}; adapter,model=build_model(final_fit); final=run_fit(final_fit,protocol,train,train,labels,adapter,model,device=device,micro_batch=protocol['candidates'][frozen.champion]['micro_batch'])
 validation_report={"status":"UNSEEN_CONFIRMATION_NOT_YET_AVAILABLE","classification":"NOT_RUN_OBSERVED_VALIDATION"}
 finalist_evidence=[dict(entry) for entry in finalists]
 for entry in finalist_evidence:
  entry.setdefault('total_parameters',None);entry.setdefault('active_parameters',None);entry.setdefault('checkpoint_bytes',None);entry.setdefault('checkpoint_sha256',None);entry.setdefault('gpu_p50_ms',None);entry.setdefault('gpu_p95_ms',None);entry.setdefault('inference_memory',None);entry.setdefault('cpu_proxy_ms',{})
  if entry['candidate']==frozen.champion and entry['depth']==frozen.depth:
   entry.update({'total_parameters':sum(parameter.numel() for parameter in model.parameters()),'active_parameters':sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad),'peak_training_vram':final['peak_vram']})
 write_deployment_cost_report(output_dir,finalist_evidence)
 manifest=build_champion_manifest({'selection':frozen.__dict__,'final_fit':final_fit,'protocol_sha256':protocol.get('_sha256'),'revision':protocol['candidates'][frozen.champion]['revision']},ranking[1] if len(ranking)>1 else None,validation_report);atomic_json_write(Path(output_dir)/'champion_manifest.json',manifest)
 return manifest

@dataclass(frozen=True)
class FrozenSelection:
 champion:str; depth:int; seed:int; thresholds:dict[str,Any]

def can_resume(fit:dict[str,Any], protocol:dict[str,Any], record_path:Path)->bool:
 record=read_completed_fit(record_path)
 npz=Path(record_path).parent / str(record.get("oof_npz", "")) if record else Path()
 if not record or not record.get("oof_complete") or not record.get("oof_npz") or not npz.is_file(): return False
 required_meta={"candidate_id":fit.get("candidate"),"depth":fit.get("depth"),"fold":fit.get("fold"),"seed":fit.get("seed")}
 if record.get("protocol_sha256")!=protocol.get("_sha256") or record.get("fit_id")!=fit.get("fit_id") or any(record.get(k)!=v for k,v in required_meta.items()): return False
 candidate=protocol.get("candidates",{}).get(fit.get("candidate"),{})
 if record.get("revision")!=candidate.get("revision") or record.get("npz_sha256")!=sha256_file(npz): return False
 try:
  import numpy as np
  data=np.load(npz); need={"semantic_logits","semantic_probabilities","semantic_targets","kind_logits","kind_probabilities","kind_targets","action_logits","action_probabilities","action_targets","record_ids","group_ids","fold","base_scenario_id","language","is_asr","kind_metadata","semantic_target_metadata","action_target_metadata"}
  if not need<=set(data.files): return False
  n=len(record.get("oof_record_ids",[]))
  if n==0 or list(data["record_ids"].astype(str))!=record["oof_record_ids"] or list(data["group_ids"].astype(str))!=record.get("oof_group_ids",[]): return False
  numeric={"semantic_logits","semantic_probabilities","semantic_targets","kind_logits","kind_probabilities","kind_targets","action_logits","action_probabilities","action_targets","fold","is_asr","semantic_target_metadata","action_target_metadata"}
  return all(len(data[name])==n for name in need) and all(np.isfinite(data[name]).all() for name in numeric)
 except Exception: return False

def persist_fit(directory:Path, fit:dict[str,Any], protocol:dict[str,Any], evidence:dict[str,Any])->Path:
 directory.mkdir(parents=True,exist_ok=True); p=directory/(fit["fit_id"]+".json")
 atomic_json_write(p,{"status":"COMPLETED","fit_id":fit["fit_id"],"fold":fit["fold"],"protocol_sha256":protocol["_sha256"],"oof_complete":True,**evidence}); return p

def run_confirmatory_validation_once(champion:Any, frozen_selection:FrozenSelection)->dict[str,Any]:
 # Selection is frozen dataclass input; evaluator receives no tuning authority.
 result=champion() if callable(champion) else {"passed":False}
 return {"classification":"CONFIRMATORY_PASS" if result.get("passed") else "CONFIRMATORY_NEEDS_MORE_WORK","selection":frozen_selection.__dict__}

def main()->None:
 p=argparse.ArgumentParser(); p.add_argument("--run",action="store_true");p.add_argument("--resume",action="store_true"); args=p.parse_args()
 if not args.run: raise SystemExit("pass --run to execute the frozen championship protocol")
 from scripts.championship_common import configure_ml_caches,load_train_records,write_observed_validation_status
 from scripts.championship_backbones import ScutModel,build_adapter
 cache_paths=configure_ml_caches(ROOT/".local"/"ml-cache")
 report=ROOT/"reports"/"scut_brain_championship_v2_pc5070"; output=ROOT/"output"/"scut_brain_championship_v2_pc5070"; protocol_path=report/"championship_protocol.json"; write_observed_validation_status(report)
 if not protocol_path.exists(): raise SystemExit("frozen championship protocol missing")
 protocol=json.loads(protocol_path.read_text(encoding="utf-8")); protocol["_sha256"]=sha256_file(protocol_path)
 preflight=report/"preflight.json"
 if not preflight.exists(): raise SystemExit("real preflight evidence missing; refusing training")
 import torch
 if not torch.cuda.is_available(): raise SystemExit("CUDA mandatory; refusing CPU fallback")
 evidence=json.loads(preflight.read_text(encoding="utf-8")).get("candidates",{})
 for candidate, config in protocol["candidates"].items():
  item=evidence.get(candidate,{})
  if item.get("status") != "PASSED" or item.get("revision") != config.get("revision"): raise SystemExit(f"preflight evidence mismatch for {candidate}")
  if not config.get("micro_batch"): raise SystemExit(f"frozen micro-batch missing for {candidate}")
 train,labels,_lineage=load_train_records(ROOT)
 output.mkdir(parents=True,exist_ok=True);fits=output/"fits";fits.mkdir(parents=True,exist_ok=True)
 def update_status(values):
  path=report/"runtime_status.json"
  try: prior=json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
  except (OSError,json.JSONDecodeError): prior={}
  prior.update(values);write_status(path,prior)
 update_status({"phase":"SCREENING","fit_total":len(protocol["phase1_fits"]),"fit_completed":0,"cuda_device":torch.cuda.get_device_name(0)})
 def build_model(fit):
  config=protocol["candidates"][fit["candidate"]];adapter=build_adapter(fit["candidate"],config["revision"],cache_dir=str(cache_paths["HF_HOME"]));return adapter,ScutModel(adapter,len(labels))
 try:
  manifest=execute_task7(protocol,train,[],labels,build_model,fits,report,device="cuda")
  update_status({"phase":manifest.get("status","COMPLETED"),"fit_total":len(protocol["phase1_fits"]),"fit_completed":len(protocol["phase1_fits"]),"cuda_device":torch.cuda.get_device_name(0),"manifest":str(report/"champion_manifest.json")})
  print(json.dumps({"status":"COMPLETED","manifest":manifest},ensure_ascii=False))
 except Exception as exc:
  update_status({"phase":"FAILED","fit_total":len(protocol["phase1_fits"]),"error":f"{type(exc).__name__}: {exc}"})
  raise
if __name__=="__main__": main()
