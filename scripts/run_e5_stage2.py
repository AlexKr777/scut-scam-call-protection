"""Stage-2, TRAIN/VALIDATION-only partial fine tuning for SCUT E5.

This intentionally never reads the historical TEST split or creates a fresh
holdout.  It is an experimental artifact runner, not production inference.
"""
from __future__ import annotations
import argparse, hashlib, json, os, random, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import psutil, torch
from sklearn.model_selection import GroupKFold
from torch import nn
from torch.utils.data import DataLoader
from transformers import AutoModel, AutoTokenizer

ROOT=Path(__file__).resolve().parents[1]; V3=ROOT/'experiments/semantic_corpus_v3.json'; EXT=ROOT/'experiments/semantic_training_extension_v1.json'
MODEL=ROOT/'.local/models/multilingual-e5-base'; OUT=ROOT/'output/scut_semantic_brain_v2'; REP=ROOT/'reports/scut_semantic_brain_v2'
ACTION={'CREDENTIAL_DISCLOSURE','MONEY_OR_ASSET_MOVEMENT','REMOTE_DEVICE_ACCESS','AUTHORIZATION_OR_APPROVAL','LINK_OR_QR_ACTION','CASH_OR_COURIER_HANDOFF','LOAN_OR_CREDIT_ACTION','CRYPTO_OR_GIFT_VALUE_TRANSFER','PERSONAL_DATA_DISCLOSURE'}
KIND={'dangerous':0,'protective':1,'legitimate':2}

def dump(p,x): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def seed(x):
 random.seed(x);np.random.seed(x);torch.manual_seed(x)
 if torch.cuda.is_available(): torch.cuda.manual_seed_all(x)
def target(r):
    """An active user-directed harmful action, excluding quotation/hypothesis/negation."""
    q=set(r['labels']);return int(bool(q&ACTION) and {'ACTUAL_REQUEST','DIRECTED_AT_USER'}<=q and not bool(q&{'NEGATION','QUOTATION','HYPOTHETICAL'}))
def manipulation_only(r):
    q=set(r['labels']); return bool(q- ACTION) and not bool(q&ACTION) and r['kind']=='dangerous'
def packed(row,tok):
    from tail_aware_e5 import pack
    return pack(row['turns'],tok,384)
class Net(nn.Module):
 def __init__(self,enc,n):
  super().__init__();self.encoder=enc;h=enc.config.hidden_size;self.drop=nn.Dropout(.1);self.semantic=nn.Linear(h,n);self.kind=nn.Linear(h,3);self.action=nn.Linear(h,1)
 def forward(self,b):
  z=self.encoder(**b).last_hidden_state;m=b['attention_mask'].unsqueeze(-1);z=nn.functional.normalize((z*m).sum(1)/m.sum(1).clamp(min=1),p=2,dim=1);z=self.drop(z);return self.semantic(z),self.kind(z),self.action(z).squeeze(-1)
def configure(net,top):
 for p in net.encoder.parameters():p.requires_grad=False
 layers=net.encoder.encoder.layer
 for layer in layers[-top:]:
  for p in layer.parameters():p.requires_grad=True
 return sum(p.numel() for p in net.encoder.parameters() if p.requires_grad)
def batches(rows,y,ki,ac,tok,shuffle,bs):
 data=list(range(len(rows))); return DataLoader(data,batch_size=bs,shuffle=shuffle,collate_fn=lambda ix:({k:v for k,v in tok([packed(rows[i],tok) for i in ix],padding=True,return_tensors='pt').items()},torch.tensor(y[ix]),torch.tensor(ki[ix]),torch.tensor(ac[ix],dtype=torch.float32)))
def metrics(pred,truth,labels):
 pred=np.asarray(pred,dtype=bool);truth=np.asarray(truth,dtype=bool)
 def one(a,b):
  tp=int((a&b).sum());fp=int((a&~b).sum());fn=int((~a&b).sum());p=tp/(tp+fp) if tp+fp else 0.;r=tp/(tp+fn) if tp+fn else 0.;return {'tp':tp,'fp':fp,'fn':fn,'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0.}
 per={};vals=[]
 for j,l in enumerate(labels): x=one(pred[:,j],truth[:,j]);x['support']=int(truth[:,j].sum());per[l]=x;vals.append(x)
 return {'micro':one(pred,truth),'macro':{k:float(np.mean([v[k] for v in vals])) for k in ('precision','recall','f1')},'exact_match':float(np.all(pred==truth,1).mean()),'per_label':per}
def safety(rows,ap,at):
 def rate(mask): return float(ap[mask].mean()) if mask.any() else None
 x=(ap.astype(bool)&at).sum(); fp=(ap.astype(bool)&~at).sum(); fn=(~ap.astype(bool)&at).sum();p=x/(x+fp) if x+fp else 0.;r=x/(x+fn) if x+fn else 0.
 return {'dangerous_action':{'tp':int(x),'fp':int(fp),'fn':int(fn),'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0.},'manipulation_only_action_fp_rate':rate(np.array([manipulation_only(z) for z in rows])),'protective_action_fp_rate':rate(np.array([z['kind']=='protective' for z in rows])),'legitimate_action_fp_rate':rate(np.array([z['kind']=='legitimate' for z in rows]))}
def fit(train,valid,labels,top,s,dev,bs,epochs=3):
 seed(s); tok=AutoTokenizer.from_pretrained(MODEL,local_files_only=True);net=Net(AutoModel.from_pretrained(MODEL,local_files_only=True),len(labels)).to(dev);n=configure(net,top)
 li={x:i for i,x in enumerate(labels)}; y=lambda rs:np.array([[int(x in r['labels']) for x in labels] for r in rs],np.float32); ty,vy=y(train),y(valid);tk=np.array([KIND[r['kind']] for r in train]);vk=np.array([KIND[r['kind']] for r in valid]);ta=np.array([target(r) for r in train]);va=np.array([target(r) for r in valid])
 pos=ty.sum(0);sem=nn.BCEWithLogitsLoss(pos_weight=torch.tensor(np.clip((len(ty)-pos)/np.maximum(pos,1),1,12),dtype=torch.float32,device=dev)); kind=nn.CrossEntropyLoss(weight=torch.tensor(np.clip(len(tk)/(3*np.bincount(tk,minlength=3)),.5,4),dtype=torch.float32,device=dev)); act=nn.BCEWithLogitsLoss(pos_weight=torch.tensor(min((len(ta)-ta.sum())/max(ta.sum(),1),6),dtype=torch.float32,device=dev))
 # One head-only epoch followed by requested partial adaptation.
 for p in net.encoder.parameters():p.requires_grad=False
 hist=[];grad=None;before=torch.cat([p.detach().flatten()[:16] for p in net.encoder.encoder.layer[-top:].parameters()]).cpu().numpy().tobytes();best=None
 for phase,count in [('warmup',1),('finetune',epochs)]:
  if phase=='finetune': configure(net,top)
  opt=torch.optim.AdamW([{'params':[p for p in net.encoder.parameters() if p.requires_grad],'lr':3e-6},{'params':list(net.semantic.parameters())+list(net.kind.parameters())+list(net.action.parameters())+list(net.drop.parameters()),'lr':5e-4}],weight_decay=.01)
  for ep in range(count):
   net.train(); losses=[]
   for b,a,c,d in batches(train,ty,tk,ta,tok,True,bs):
    o=net({k:v.to(dev) for k,v in b.items()});loss=sem(o[0],a.to(dev))+.35*kind(o[1],c.to(dev))+.5*act(o[2],d.to(dev));opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),1.0);grad=float(sum((p.grad.abs().sum().item() for p in net.encoder.parameters() if p.requires_grad and p.grad is not None)));opt.step();losses.append(float(loss))
   net.eval();sp=[];kp=[];ap=[]
   with torch.no_grad():
    for b,_,_,_ in batches(valid,vy,vk,va,tok,False,bs):
     o=net({k:v.to(dev) for k,v in b.items()});sp.append(torch.sigmoid(o[0]).cpu().numpy());kp.append(torch.softmax(o[1],1).cpu().numpy());ap.append(torch.sigmoid(o[2]).cpu().numpy())
   pr=np.vstack(sp); ad=np.hstack(ap); score=safety(valid,ad>=.5,va)['dangerous_action']['recall']; hist.append({'phase':phase,'epoch':ep+1,'loss':float(np.mean(losses)),'action_recall_at_0_5':score})
   if best is None or score>best[0]:best=(score,{k:v.detach().clone() for k,v in net.state_dict().items()})
 net.load_state_dict(best[1]);after=torch.cat([p.detach().flatten()[:16] for p in net.encoder.encoder.layer[-top:].parameters()]).cpu().numpy().tobytes()
 net.eval();sp=[];kp=[];ap=[]
 with torch.no_grad():
  for b,_,_,_ in batches(valid,vy,vk,va,tok,False,bs):
   o=net({k:v.to(dev) for k,v in b.items()});sp.append(torch.sigmoid(o[0]).cpu().numpy());kp.append(torch.softmax(o[1],1).cpu().numpy());ap.append(torch.sigmoid(o[2]).cpu().numpy())
 return net,tok,{'history':hist,'encoder_trainable_parameters':n,'encoder_gradient_l1':grad,'weights_changed':before!=after,'semantic_prob':np.vstack(sp),'action_prob':np.hstack(ap),'truth':vy,'action_truth':va}
def thresholds(prob,truth,labels):
 out={}
 for j,l in enumerate(labels):out[l]=max((.25,.4,.5,.6),key=lambda x:metrics((prob[:,j:j+1]>=x),truth[:,j:j+1],[l])['micro']['f1']) if truth[:,j].sum()>=2 else .5
 return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--quick',action='store_true');ap.add_argument('--device',choices=('cpu','cuda'),default='cpu');ap.add_argument('--output-dir',type=Path,default=OUT);ap.add_argument('--report-dir',type=Path,default=REP);ap.add_argument('--batch-size',type=int,default=2);args=ap.parse_args();started=time.time();out=args.output_dir;rep=args.report_dir
 if args.device=='cuda' and not torch.cuda.is_available(): raise RuntimeError('CUDA was explicitly requested but is unavailable; refusing CPU fallback.')
 dev=torch.device(args.device); out.mkdir(parents=True,exist_ok=True)
 v3=json.loads(V3.read_text(encoding='utf8'));ext=json.loads(EXT.read_text(encoding='utf8'))
 # Variants deliberately inherit base metadata in the immutable corpus, so
 # materialize kind only in these in-memory training views.
 kinds={r['id']:r['kind'] for r in v3['bases']+ext['bases']}
 rows=[]
 for r in v3['bases']+v3['variants']+ext['bases']+ext['variants']:
  q=dict(r);q['kind']=q.get('kind',kinds[q['base_scenario_id']]);rows.append(q)
 train=[r for r in rows if r['split']=='train'];valid=[r for r in rows if r['split']=='validation'];labels=sorted({x for r in train for x in r['labels']})
 assert all(r['split']=='train' for r in train) and not set(r['base_scenario_id'] for r in train)&set(r['base_scenario_id'] for r in valid)
 # grouped CV performs bounded architecture screening strictly within TRAIN.
 groups=np.array([r['base_scenario_id'] for r in train]);cv=[]
 for top in (2,4):
  for fold,(a,b) in enumerate(GroupKFold(3).split(train,groups=groups),1):
   _,_,z=fit([train[i] for i in a],[train[i] for i in b],labels,top,17+fold,dev,args.batch_size,1 if args.quick else 2);sa=safety([train[i] for i in b],z['action_prob']>=.5,z['action_truth']);cv.append({'candidate':f'top_{top}','fold':fold,'safety':sa,'semantic':metrics(z['semantic_prob']>=.5,z['truth'],labels),'fine_tuning_proof':{k:z[k] for k in ('encoder_trainable_parameters','encoder_gradient_l1','weights_changed')}})
 dump(out/'cv_results.json',cv); chosen=max((2,4),key=lambda top:np.mean([x['safety']['dangerous_action']['recall'] for x in cv if x['candidate']==f'top_{top}']))
 seeds=[]
 for s in (17,29,43):
  _,_,z=fit(train,valid,labels,chosen,s,dev,args.batch_size,1 if args.quick else 3);seeds.append({'seed':s,'dangerous_recall':safety(valid,z['action_prob']>=.5,z['action_truth'])['dangerous_action']['recall'],'semantic_macro_f1':metrics(z['semantic_prob']>=.5,z['truth'],labels)['macro']['f1']})
 dump(out/'seed_stability.json',{'selected_candidate':f'top_{chosen}','runs':seeds,'mean_dangerous_recall':float(np.mean([x['dangerous_recall'] for x in seeds])),'std_dangerous_recall':float(np.std([x['dangerous_recall'] for x in seeds]))})
 net,tok,z=fit(train,valid,labels,chosen,17,dev,args.batch_size,2 if args.quick else 4);th=thresholds(z['semantic_prob'],z['truth'],labels);pred=z['semantic_prob']>=np.array([th[x] for x in labels]);ath=.5;val={'semantic':metrics(pred,z['truth'],labels),'safety':safety(valid,z['action_prob']>=ath,z['action_truth']),'thresholds':th,'action_threshold':ath}
 dump(out/'selected_thresholds.json',{'semantic':th,'dangerous_action':ath});dump(out/'validation_metrics.json',val); ck=out/'selected_model'/'model.pt';ck.parent.mkdir(parents=True,exist_ok=True);torch.save({'state':net.state_dict(),'labels':labels,'top_layers':chosen,'max_length':384},ck);cfg={'base_encoder':'intfloat/multilingual-e5-base','local_path':str(MODEL),'preprocessing':'scripts/tail_aware_e5.py','max_tokens':384,'heads':['semantic multi-label','kind','dangerous_action_present'],'top_trainable_layers':chosen,'labels':labels};dump(ck.parent/'selected_config.json',cfg);dump(ck.parent/'selected_thresholds.json',{'semantic':th,'dangerous_action':ath});dump(ck.parent/'training_history.json',z['history']);dump(ck.parent/'validation_metrics.json',val);dump(ck.parent/'model_selection.json',{'candidate':f'top_{chosen}','cv':cv,'seeds':seeds})
 # serialization smoke, plus latency from the frozen artifact.
 torch.load(ck,weights_only=True);t0=time.perf_counter(); _=Net(AutoModel.from_pretrained(MODEL,local_files_only=True),len(labels));load=time.perf_counter()-t0; warm=[]
 for r in valid[:min(12,len(valid))]:
  q=time.perf_counter();net.eval();
  with torch.no_grad():net({k:v.to(dev) for k,v in tok([packed(r,tok)],return_tensors='pt').items()})
  warm.append((time.perf_counter()-q)*1000)
 torch.cuda.synchronize() if dev.type=='cuda' else None
 lat={'model_load_seconds':load,'warm_inference_ms':{'p50':float(np.percentile(warm,50)),'p95':float(np.percentile(warm,95)),'max':float(max(warm))},'rss_mb':psutil.Process().memory_info().rss/1048576,'checkpoint_bytes':ck.stat().st_size,'device':str(dev)};dump(out/'latency_precheck.json',lat)
 manifest={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'dataset_hashes':{'v3':sha(V3),'extension':sha(EXT),'blueprint':sha(REP/'fresh_holdout_blueprint.json')},'training_counts':{'original_v3_train':sum(r['split']=='train' for r in v3['bases']+v3['variants']),'extension_train':len(ext['bases'])+len(ext['variants']),'total':len(train),'validation':len(valid)},'architecture':cfg,'cv_strategy':'3-fold GroupKFold by base_scenario_id, train-only','candidate_matrix':['top_2','top_4'],'selected_candidate':f'top_{chosen}','checkpoint':str(ck),'checkpoint_sha256':sha(ck),'thresholds':th,'validation_metrics':val,'fine_tuning_proof':{k:z[k] for k in ('encoder_trainable_parameters','encoder_gradient_l1','weights_changed')},'latency_precheck':lat,'duration_seconds':time.time()-started,'model_frozen_at':datetime.now(timezone.utc).isoformat()};dump(rep/'stage2_manifest.json',manifest);print(json.dumps({'manifest':str(rep/'stage2_manifest.json'),'selected':f'top_{chosen}','duration_seconds':manifest['duration_seconds'],'device':str(dev)},indent=2))
if __name__=='__main__':main()
