"""Realtime-paced saved-fixture smoke through the contextual caller path."""
from __future__ import annotations
import json, statistics, subprocess, sys, threading, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from backend.acoustic_validation import PHRASES, semantic_fields, wav_to_guarded_pcm, write_report
from backend.config import caller_asr_config
from backend.contextual_streaming_asr import ContextualStreamingCallerASR
from backend.dual_pass_asr import ASRText
from backend.guarded_audio import transcribe_fast_details
from backend.realtime_pipeline import DualChannelPipeline

def snapshot():
    try:
        x=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu,temperature.gpu,clocks_throttle_reasons.active','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True,timeout=4).stdout.splitlines()[0].split(',')
        return {'vramMiB':int(x[0]),'utilizationPct':int(x[1]),'temperatureC':int(x[2]),'throttle':x[3].strip()}
    except Exception:return None
class Telemetry:
    def __init__(self):self.rows=[];self.stop=threading.Event();self.t=threading.Thread(target=self.run,daemon=True)
    def run(self):
        while not self.stop.is_set():
            if (x:=snapshot()):self.rows.append(x)
            self.stop.wait(.2)
    def __enter__(self):self.t.start();return self
    def __exit__(self,*_):self.stop.set();self.t.join(3)
    def summary(self):return {'samples':len(self.rows),'peakVramMiB':max(x['vramMiB'] for x in self.rows),'peakUtilizationPct':max(x['utilizationPct'] for x in self.rows),'peakTemperatureC':max(x['temperatureC'] for x in self.rows),'thermalThrottlingObserved':any('Not Active' not in x['throttle'] for x in self.rows)} if self.rows else {'available':False}
def main():
    profile=caller_asr_config()
    if profile != {'profile':'turbo_cuda','model':'large-v3-turbo','device':'cuda','computeType':'float16'}: raise RuntimeError(f'Expected Turbo CUDA FP16 profile, got {profile}')
    import ctranslate2
    if ctranslate2.get_cuda_device_count()<1:raise RuntimeError('CUDA unavailable; smoke test refuses fallback')
    path=ROOT/'diagnostics'/'tests'/'scam_acoustic_fixtures'/'10_ru_protective__clean.wav';pcm,duration=wav_to_guarded_pcm(path)
    language,kind,source,required=PHRASES[9]; submitted={}; timings={}; started=time.perf_counter()
    def fast(raw,locked):
        decode_started=time.perf_counter(); timings.setdefault('queueWaitSeconds',round(decode_started-submitted.pop('at',decode_started),4))
        x=transcribe_fast_details(raw,profile['model'],language=locked,device=profile['device'],compute_type=profile['computeType'])
        return ASRText(x['text'],x['language'],float(x['languageProbability']),{'segments':x['segments']})
    engine=ContextualStreamingCallerASR(fast,language,6000,1000,500); last_speech_wall=None
    original_offer=engine.scheduler.offer
    def offer(item):submitted['at']=time.perf_counter();original_offer(item)
    engine.scheduler.offer=offer
    with Telemetry() as telemetry:
        for offset in range(0,duration,250):
            end=min(duration,offset+250);frame=pcm[offset*192:end*192]
            if DualChannelPipeline.has_speech(frame):last_speech_wall=time.perf_counter()
            engine.ingest_caller(frame,offset,end)
            if engine.metrics and engine.metrics[-1]['kind']=='FINAL' and 'finalTranscriptReadySeconds' not in timings:
                ready=time.perf_counter();timings['finalTranscriptReadySeconds']=round(ready-started,3);timings['endOfSpeechToFinalReadySeconds']=round(ready-(last_speech_wall or ready),3)
            row=engine.drain_fast_once()
            if row and 'firstUsefulTranscriptReadySeconds' not in timings and all(semantic_fields(row['fastPartial'],language,required).values()):timings['firstUsefulTranscriptReadySeconds']=round(time.perf_counter()-started,3)
            target=started+end/1000;time.sleep(max(0,target-time.perf_counter()))
        if 'finalTranscriptReadySeconds' not in timings:
            engine.ingest_caller(b'\0'*96000,duration,duration+500);ready=time.perf_counter();timings['finalTranscriptReadySeconds']=round(ready-started,3);timings['endOfSpeechToFinalReadySeconds']=round(ready-(last_speech_wall or ready),3)
    fields=semantic_fields(engine.stable_fast,language,required)
    report={'experiment':'TURBO_SAVED_AUDIO_CONTEXTUAL_STREAMING_SMOKE','fixture':str(path.relative_to(ROOT)),'profile':profile,'cudaDeviceCount':int(ctranslate2.get_cuda_device_count()),'wallClock':timings,'streaming':{'transcriptProduced':bool(engine.stable_fast),'finalTranscript':engine.stable_fast,'semanticFields':fields,'pass':all(fields.values()),'maxPendingJobs':engine.scheduler.max_pending,'coalescedPartialJobs':engine.scheduler.coalesced,'boundedBacklog':engine.scheduler.max_pending<=1,'finalizerObviousCorruption':engine.stable_fast != engine.metrics[-1]['wholeUtteranceTranscript']},'gpu':telemetry.summary(),'metrics':engine.metrics}
    out=ROOT/'diagnostics'/f'turbo_saved_audio_streaming_smoke_{time.strftime("%Y%m%d-%H%M%S")}.json';write_report(report,out);print(json.dumps({'output':str(out),'pass':report['streaming']['pass'],'wallClock':report['wallClock'],'gpu':report['gpu']},ensure_ascii=False))
if __name__=='__main__':main()
