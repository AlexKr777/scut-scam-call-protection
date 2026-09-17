"""Experimental deterministic, turn-aware tail-first E5 packing."""
def pack(turns,tokenizer,max_length=384):
 text=lambda xs:" ".join(f"[{s}] {t}" for s,t in xs)
 whole="query: "+text(turns)
 if len(tokenizer(whole,add_special_tokens=True)["input_ids"])<=max_length:return whole
 chosen=[]; head=turns[:1]
 # An oversized opening turn must never evict the newest request.
 if len(tokenizer("query: "+text(head)+" [CONTEXT_OMITTED] "+text(turns[-1:]),add_special_tokens=True)["input_ids"])>max_length:
  head=[]
 for turn in reversed(turns):
  candidate="query: "+text(head)+" [CONTEXT_OMITTED] "+text([turn]+chosen)
  if len(tokenizer(candidate,add_special_tokens=True)["input_ids"])>max_length:break
  chosen.insert(0,turn)
 return "query: "+text(head)+" [CONTEXT_OMITTED] "+text(chosen)
