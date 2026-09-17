"""Isolated frozen-E5 multi-label experiment.  It never imports RiskPolicy."""
from __future__ import annotations
import json, random, statistics, sys, time
from collections import Counter
from pathlib import Path
import numpy as np
import psutil, torch
from torch import nn
from transformers import AutoModel, AutoTokenizer

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from backend.semantic_dataset import development_cases
from scripts.audit_supervised_corpus import LABELS, split
MODEL=ROOT/'.local/models/multilingual-e5-base'; OUT=ROOT/'reports/scut_e5_frozen_experiment.json'
ACTION={"CREDENTIAL_DISCLOSURE","MONEY_OR_ASSET_MOVEMENT","REMOTE_DEVICE_ACCESS","AUTHORIZATION_OR_APPROVAL","LINK_OR_QR_ACTION","CASH_OR_COURIER_HANDOFF","LOAN_OR_CREDIT_ACTION","CRYPTO_OR_GIFT_VALUE_TRANSFER","PERSONAL_DATA_DISCLOSURE"}

def text(case): return 'query: ' + ' '.join(f'[{s}] {t}' for s,t in case.turns)
def pooled(model, tok, rows):
    allv=[]; model.eval()
    with torch.no_grad():
      for i in range(0,len(rows),8):
        x=tok([text(r) for r in rows[i:i+8]],padding=True,truncation=True,max_length=256,return_tensors='pt').to('cuda' if torch.cuda.is_available() else 'cpu')
        h=model(**x).last_hidden_state; m=x['attention_mask'].unsqueeze(-1)
        v=(h*m).sum(1)/m.sum(1).clamp(min=1); allv.append(torch.nn.functional.normalize(v,p=2,dim=1).cpu())
    return torch.cat(allv).numpy()
def f1(p,y):
    tp=((p==1)&(y==1)).sum(); fp=((p==1)&(y==0)).sum(); fn=((p==0)&(y==1)).sum()
    return float(2*tp/max(1,2*tp+fp+fn))
def main():
  raw=development_cases(); rows=[]
  for i,c in enumerate(raw):
    # Ephemeral attributes are attached only to these in-memory fixture values;
    # the source fixture module is never written or used by production here.
    sc=i//10; object.__setattr__(c,'labels',LABELS[sc]); object.__setattr__(c,'base',f'scenario-{sc:02d}'); object.__setattr__(c,'bucket',split(c.base)); rows.append(c)
  labels=sorted(set().union(*LABELS)); li={v:i for i,v in enumerate(labels)}
  model=AutoModel.from_pretrained(MODEL).to('cuda' if torch.cuda.is_available() else 'cpu'); tok=AutoTokenizer.from_pretrained(MODEL)
  started=time.perf_counter(); X=pooled(model,tok,rows); encode_ms=(time.perf_counter()-started)*1000/len(rows); del model; torch.cuda.empty_cache()
  Y=np.zeros((len(rows),len(labels)),np.float32)
  for i,r in enumerate(rows):
    for z in r.labels:Y[i,li[z]]=1
  ix={s:np.array([i for i,r in enumerate(rows) if r.bucket==s]) for s in ('train','validation','test')}
  def run(seed):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    head=nn.Sequential(nn.Dropout(.10),nn.Linear(X.shape[1],len(labels)))
    tr=torch.tensor(ix['train']); xx=torch.tensor(X); yy=torch.tensor(Y)
    pos=Y[ix['train']].sum(0); weight=torch.tensor(np.clip((len(tr)-pos)/np.maximum(pos,1),1,20),dtype=torch.float32)
    opt=torch.optim.AdamW(head.parameters(),lr=2e-3,weight_decay=1e-3); lossfn=nn.BCEWithLogitsLoss(pos_weight=weight)
    best=None; stale=0
    for epoch in range(60):
      head.train(); opt.zero_grad(); loss=lossfn(head(xx[tr]),yy[tr]);loss.backward();opt.step()
      with torch.no_grad():
       pv=torch.sigmoid(head(xx[ix['validation']])).numpy(); score=np.mean([f1((pv[:,j]>=.5).astype(int),Y[ix['validation'],j].astype(int)) for j in range(len(labels)) if Y[ix['validation'],j].sum()])
      if best is None or score>best[0]:best=(score,{k:v.detach().clone() for k,v in head.state_dict().items()},epoch);stale=0
      else: stale+=1
      if stale>=8:break
    head.load_state_dict(best[1]);
    with torch.no_grad(): p=torch.sigmoid(head(xx)).numpy()
    # Per-label thresholds are chosen only from validation F1.
    th=np.full(len(labels),.5)
    for j in range(len(labels)):
      yv=Y[ix['validation'],j]
      # A label unseen in training has no learned semantic meaning; suppress it
      # rather than turning a low default threshold into a fabricated positive.
      if Y[ix['train'],j].sum()==0: th[j]=1.1
      elif yv.sum(): th[j]=max((.25,.5,.75),key=lambda q:f1((p[ix['validation'],j]>=q).astype(int),yv.astype(int)))
    return p,th,best[2],best[0]
  runs=[]
  for seed in (17,23,41):
    p,th,epoch,val_score=run(seed); pred=p>=th; test=ix['test']; per={}
    for j,n in enumerate(labels):
      y=Y[test,j].astype(int); q=pred[test,j].astype(int)
      if y.sum() or q.sum():
       tp=((q==1)&(y==1)).sum();fp=((q==1)&(y==0)).sum();fn=((q==0)&(y==1)).sum(); per[n]={"support":int(y.sum()),"precision":round(float(tp/max(1,tp+fp)),3),"recall":round(float(tp/max(1,tp+fn)),3),"f1":round(f1(q,y),3),"threshold":float(th[j])}
    action_idx=[li[x] for x in ACTION if x in li]; dangerous=(Y[test][:,action_idx].sum(1)>0); action_pred=(pred[test][:,action_idx].sum(1)>0)
    safe=np.array([rows[i].kind=='safe' for i in test]);
    fails=[{"id":rows[i].id,"base":rows[i].base,"language":rows[i].language,"text":text(rows[i]),"expected":sorted(rows[i].labels),"predicted":[labels[j] for j in range(len(labels)) if pred[i,j]]} for i in test if (Y[i]>0).any() and not pred[i,Y[i].astype(bool)].any()]
    runs.append({"seed":seed,"bestValidationMacroF1":round(float(val_score),3),"bestEpoch":epoch,"dangerousActionRecall":round(float(action_pred[dangerous].mean()),3) if dangerous.any() else None,"protectiveFalsePositiveRate":round(float(action_pred[safe].mean()),3) if safe.any() else None,"perLabel":per,"failingExamples":fails[:12]})
  report={"experiment":"frozen intfloat/multilingual-e5-base + dropout linear multi-label heads","encoderFrozen":True,"seeds":runs,"embeddingDimension":int(X.shape[1]),"encodingMsPerExample":round(encode_ms,2),"processRamMB":round(psutil.Process().memory_info().rss/1048576,1),"split":{"train":len(ix['train']),"validation":len(ix['validation']),"test":len(ix['test'])},"criticalLimitation":"Only 30 base groups; several labels have no positive training or test support. Results are selection evidence only, not a generalization claim."}
  OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
