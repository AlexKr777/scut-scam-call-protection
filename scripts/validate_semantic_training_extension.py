"""Reader-only integrity validation for the external train-only extension."""
from __future__ import annotations
import json,re,sys
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.validate_semantic_corpus_v3 import ALLOWED_LABELS,LANGUAGES,SPLITS,KINDS,SPEAKERS
def norm(r):return re.sub(r"[^\w]+","", " ".join(t for _,t in r["turns"]).casefold())
def main():
 ext=json.loads((ROOT/"experiments/semantic_training_extension_v1.json").read_text(encoding="utf8")); v3=json.loads((ROOT/"experiments/semantic_corpus_v3.json").read_text(encoding="utf8"))
 err=[]; bases=ext.get("bases",[]); variants=ext.get("variants",[])
 if set(ext)!={"bases","variants"}:err.append("top-level shape")
 ids=[r.get("id") for r in bases+variants]
 if len(ids)!=len(set(ids)):err.append("duplicate ids")
 bm={r.get("id"):r for r in bases}
 seen=defaultdict(list)
 for r in bases:
  if r.get("base_scenario_id")!=r.get("id") or r.get("split")!="train":err.append("invalid base lineage/split "+str(r.get("id")))
  if r.get("language") not in LANGUAGES or r.get("kind") not in KINDS or set(r.get("labels",[]))-ALLOWED_LABELS:err.append("invalid base metadata "+str(r.get("id")))
  if not r.get("turns") or not all(isinstance(x,list) and len(x)==2 and x[0] in SPEAKERS and isinstance(x[1],str) for x in r["turns"]):err.append("invalid turns "+str(r.get("id")))
 for r in variants:
  b=bm.get(r.get("base_scenario_id"))
  if not b or r.get("variant_type")!="asr_corrupted" or any(r.get(k)!=b.get(k) for k in ("split","language","labels")):err.append("variant lineage "+str(r.get("id")))
  if b and norm(r)==norm(b):err.append("unchanged ASR "+r["id"])
 for r in bases+variants:seen[norm(r)].append(r["id"])
 if any(len(x)>1 for x in seen.values()):err.append("normalized duplicate")
 v3norm={norm(r) for r in v3["bases"]+v3["variants"]}
 if any(norm(r) in v3norm for r in bases):err.append("overlap with v3")
 report={"base_count":len(bases),"variant_count":len(variants),"language_base_counts":dict(Counter(r["language"] for r in bases)),"language_variant_counts":dict(Counter(r["language"] for r in variants)),"kind_counts":dict(Counter(r["kind"] for r in bases)),"errors":err,"valid":not err}
 p=ROOT/"reports/scut_semantic_brain_v2/training_extension_validation.json";p.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8");print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if not err else 1
if __name__=="__main__":raise SystemExit(main())
