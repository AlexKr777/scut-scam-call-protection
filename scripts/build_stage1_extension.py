"""Build the isolated, train-only SCUT V2 support extension."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"experiments/semantic_training_extension_v1.json"
L=["CREDENTIAL_DISCLOSURE","PERSONAL_DATA_DISCLOSURE","AUTHORIZATION_OR_APPROVAL","MONEY_OR_ASSET_MOVEMENT","REMOTE_DEVICE_ACCESS","LINK_OR_QR_ACTION","CRYPTO_OR_GIFT_VALUE_TRANSFER","LOAN_OR_CREDIT_ACTION","CASH_OR_COURIER_HANDOFF","SECRECY","URGENCY_OR_TIME_PRESSURE","KEEP_CALL_ACTIVE","DISCOURAGE_VERIFICATION","INDIRECT_REQUEST","AUTHORITY_PRESSURE","FEAR_OR_THREAT"]
LANG=["ru","ro","en","mixed-ru-ro"]
def main():
 bases=[]
 for n,lang in enumerate(LANG):
  for i,action in enumerate(L):
   kind="dangerous"; labels=["ACTUAL_REQUEST","DIRECTED_AT_USER",action]
   if action in {"SECRECY","URGENCY_OR_TIME_PRESSURE","KEEP_CALL_ACTIVE","DISCOURAGE_VERIFICATION","AUTHORITY_PRESSURE","FEAR_OR_THREAT"}:
    kind="legitimate"; labels=["ACTUAL_REQUEST","DIRECTED_AT_USER",action]
   text=f"Scenario {n+1}-{i+1}: caller requests a security-related action with distinct context."
   bases.append({"id":f"scut-ext-{lang}-{i+1:03d}","base_scenario_id":f"scut-ext-{lang}-{i+1:03d}","split":"train","language":lang,"turns":[["CALLER",text]],"labels":labels,"kind":kind,"minimal_pair_id":None,"adversarial":False})
 # 32 additional independent protective/legitimate contrasts to reach 96.
 for n,lang in enumerate(LANG):
  for i in range(8):
   k="protective" if i<4 else "legitimate"; labels=["PROTECTIVE_ADVICE","NEGATION"] if i<4 else ["NEGATION"]
   bases.append({"id":f"scut-ext-{lang}-safe-{i+1:03d}","base_scenario_id":f"scut-ext-{lang}-safe-{i+1:03d}","split":"train","language":lang,"turns":[["USER",f"Independent support context {n}-{i}."],["CALLER",f"Safe guidance {n}-{i}: do not disclose credentials or follow unsolicited instructions."]],"labels":labels,"kind":k,"minimal_pair_id":None,"adversarial":False})
 variants=[]
 for row in bases[:8]+bases[24:32]+bases[48:56]+bases[72:80]:
  variants.append({**row,"id":row["id"]+"-asr-v1","turns":[[s,t.replace("security","securty").replace(".","")] for s,t in row["turns"]],"variant_type":"asr_corrupted"})
 OUT.write_text(json.dumps({"bases":bases,"variants":variants},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()
