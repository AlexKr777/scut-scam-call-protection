from __future__ import annotations
import json, sys, time, wave
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
from backend.guarded_audio import transcribe_pcm_details
from backend.realtime_pipeline import TranscriptStabilizer
p=ROOT/'diagnostics'/'guarded_system_mix_call_2.wav'
with wave.open(str(p),'rb') as w: raw=w.readframes(w.getnframes()); rate=w.getframerate(); channels=w.getnchannels(); width=w.getsampwidth(); duration=w.getnframes()/rate
configs=[]
for window,overlap in ((1.5,.5),(2.0,.5),(2.5,.5)):
    step=window-overlap; stabilizer=TranscriptStabilizer(); rows=[]; total=0.; index=0
    while index*step<duration:
        start=index*step; end=min(duration,start+window); a=int(start*rate)*channels*width; b=int(end*rate)*channels*width
        t=time.perf_counter(); out=transcribe_pcm_details(raw[a:b], vad_filter=False); elapsed=time.perf_counter()-t; total+=elapsed
        partial,stable=stabilizer.update(out['text'],end>=duration)
        rows.append({'startMs':round(start*1000),'endMs':round(end*1000),'partial':partial,'stable':stable,'asrSeconds':round(elapsed,3),'realTimeFactor':round(elapsed/(end-start),3)})
        index+=1
    configs.append({'windowSeconds':window,'overlapSeconds':overlap,'windows':rows,'totalAsrSeconds':round(total,3),'inputSeconds':duration,'overallRealTimeFactor':round(total/duration,3),'finalStable':stabilizer.stable})
report={'fixture':str(p),'durationSeconds':duration,'model':'faster-whisper-small CPU int8','configs':configs}
(ROOT/'diagnostics'/'REALTIME_CALLER_FIXTURE_BENCHMARK.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False))
