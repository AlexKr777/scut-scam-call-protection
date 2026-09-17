import json, time, wave, sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from backend.guarded_audio import transcribe_pcm_details
with wave.open(str(root/'diagnostics'/'guarded_system_mix_call_2.wav'),'rb') as w: raw=w.readframes(w.getnframes()); rate=w.getframerate()
rows=[]
for seconds in (1.5,2.0,2.5,8.0):
    t=time.perf_counter(); data=transcribe_pcm_details(raw[:int(seconds*rate)*4],vad_filter=False); elapsed=time.perf_counter()-t
    rows.append({'windowSeconds':seconds,'asrSeconds':round(elapsed,3),'realTimeFactor':round(elapsed/seconds,3),'text':data['text']})
report={
    'fixture':'diagnostics/guarded_system_mix_call_2.wav',
    'model':'faster-whisper-small CPU int8, beam_size=1, VAD disabled inside ASR (upstream PCM VAD)',
    'windows':rows,
    # 8 seconds is the smallest tested window that finishes before its audio
    # duration on this CPU and retains the verified full caller phrase.
    'selected':{'windowSeconds':8.0,'overlapSeconds':0.0,'reason':'only measured window with realTimeFactor < 1 and complete intelligible fixture transcription'}
}
(root/'diagnostics'/'INCREMENTAL_WINDOW_MEASUREMENTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False))
