"""Fixed-logit local NLI runtime; no transcript is ever interpreted as instructions."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import json
import threading
from pathlib import Path
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

class NliLabel(str, Enum): ENTAILMENT="ENTAILMENT"; CONTRADICTION="CONTRADICTION"; UNKNOWN="UNKNOWN"
@dataclass(frozen=True)
class NliResult:
    label: NliLabel; entailment: float; contradiction: float; unknown: float

def label_mapping_from_config(config: dict) -> dict[int,NliLabel]:
    raw=config.get("id2label",{}); result={}
    aliases={"entailment":NliLabel.ENTAILMENT,"contradiction":NliLabel.CONTRADICTION,"neutral":NliLabel.UNKNOWN,"unknown":NliLabel.UNKNOWN}
    for key,value in raw.items():
        label=aliases.get(str(value).lower())
        if label is None: raise ValueError("unsupported NLI label: "+str(value))
        result[int(key)]=label
    if set(result.values()) != {NliLabel.ENTAILMENT,NliLabel.CONTRADICTION,NliLabel.UNKNOWN}: raise ValueError("NLI config must map entailment, contradiction and neutral")
    return result

class LocalNliRuntime:
    def __init__(self, model_dir: str|Path, max_tokens: int=256):
        root=Path(model_dir); self.max_tokens=max_tokens
        self.label_map=label_mapping_from_config(json.loads((root/"config.json").read_text(encoding="utf-8")))
        self.tokenizer=Tokenizer.from_file(str(root/"tokenizer.json"))
        self.session=ort.InferenceSession(str(root/"model_quantized.onnx"),providers=["CPUExecutionProvider"])
        self.input_names={item.name for item in self.session.get_inputs()}
    def verify_pairs(self, pairs: list[tuple[str,str]]) -> list[NliResult]:
        encoded=self.tokenizer.encode_batch([(premise,hypothesis) for premise,hypothesis in pairs])
        length=min(self.max_tokens,max(len(item.ids) for item in encoded)); ids=np.zeros((len(encoded),length),dtype=np.int64); mask=np.zeros_like(ids); types=np.zeros_like(ids)
        for row,item in enumerate(encoded):
            n=min(length,len(item.ids)); ids[row,:n]=item.ids[:n]; mask[row,:n]=item.attention_mask[:n]; types[row,:n]=item.type_ids[:n]
        inputs={"input_ids":ids,"attention_mask":mask}
        if "token_type_ids" in self.input_names: inputs["token_type_ids"]=types
        logits=self.session.run(None,inputs)[0]; shifted=logits-logits.max(axis=1,keepdims=True); probs=np.exp(shifted)/np.exp(shifted).sum(axis=1,keepdims=True)
        result=[]
        for row in probs:
            values={self.label_map[index]:float(value) for index,value in enumerate(row)}
            result.append(NliResult(max(values,key=values.get),values[NliLabel.ENTAILMENT],values[NliLabel.CONTRADICTION],values[NliLabel.UNKNOWN]))
        return result

_default_runtime=None; _default_lock=threading.Lock()
def default_runtime():
    global _default_runtime
    if _default_runtime is None:
        with _default_lock:
            if _default_runtime is None:
                root=Path(__file__).resolve().parents[1]/".local"/"models"/"mdeberta-v3-base-mnli-xnli"
                _default_runtime=LocalNliRuntime(root)
    return _default_runtime
