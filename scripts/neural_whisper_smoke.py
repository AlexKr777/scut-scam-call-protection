"""One-fixture concurrent smoke; deliberately not the historical 108-case benchmark."""
from __future__ import annotations
import json, threading, time
from pathlib import Path
import sys
import psutil
root=Path(__file__).resolve().parents[1]
if str(root) not in sys.path: sys.path.insert(0,str(root))
from backend.neural_nli import default_runtime
from backend.neural_semantics import CORE
from backend.config import caller_asr_config

fixture=root/"diagnostics"/"test_call.wav"; config=caller_asr_config(); result={"fixture":str(fixture),"asrProfile":config,"semantic":None,"whisper":None,"oom":False}
runtime=default_runtime(); pairs=[("Please move funds to another destination.",hypothesis) for _,hypothesis in CORE]
def semantic():
    started=time.perf_counter(); runtime.verify_pairs(pairs); result["semantic"]={"batchSize":len(pairs),"ms":round((time.perf_counter()-started)*1000,1)}
thread=threading.Thread(target=semantic); thread.start()
try:
    from faster_whisper import WhisperModel
    # Use configured runtime only when its model is already locally available;
    # this smoke never initiates an ASR model download.
    model=WhisperModel(config["model"],device=config["device"],compute_type=config["computeType"],local_files_only=True)
    started=time.perf_counter(); segments,_=model.transcribe(str(fixture)); text=" ".join(s.text for s in segments)
    result["whisper"]={"state":"RAN","ms":round((time.perf_counter()-started)*1000,1),"characters":len(text)}
except Exception as error:
    result["whisper"]={"state":"NOT_RUN","reason":type(error).__name__}
thread.join(); result["ramMB"]=round(psutil.Process().memory_info().rss/1048576,1)
out=root/"reports"/"scut_neural_whisper_smoke.json"; out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(result,indent=2),encoding="utf-8"); print(json.dumps(result))
