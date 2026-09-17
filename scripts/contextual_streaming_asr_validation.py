"""Re-run the existing acoustic WAV fixtures through contextual streaming ASR.

No fixture generation occurs here.  Default configuration was selected for a
bounded six-second caller context and one-second update cadence; --benchmark
evaluates the requested context/cadence grid against the exact same files.
"""
from __future__ import annotations
import argparse, json, os, sys, time, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
from backend.acoustic_validation import PHRASES, semantic_fields, wav_to_guarded_pcm, write_report
from backend.contextual_streaming_asr import ContextualStreamingCallerASR
from backend.dual_pass_asr import ASRText
from backend.guarded_audio import transcribe_pcm_details

FIXTURES=ROOT/'diagnostics'/'tests'/'scam_acoustic_fixtures'
MODEL_NAME=os.environ.get('SCUT_VALIDATION_MODEL','base')
REQUESTED_COMPUTE_TYPE='int8'

def phrase_for(path: Path):
    n=int(path.name[:2]); return PHRASES[n-1]
def gpu_memory_mib():
    try:
      value=subprocess.run(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5,check=True).stdout.splitlines()[0]
      return int(value.strip())
    except Exception: return None
def run_case(path: Path, configured: bool, context_ms: int, cadence_ms: int) -> dict:
    language, klass, source, required=phrase_for(path); pcm,duration=wav_to_guarded_pcm(path)
    def fast(raw, locked):
        x=transcribe_pcm_details(raw,vad_filter=False,model_name=MODEL_NAME,language=locked)
        return ASRText(x['text'],x['language'],float(x['languageProbability']), {
            'avg_logprob': float(x['averageLogProb']) if x['averageLogProb'] else None,
            'no_speech_probability': float(x['noSpeechProbability']) if x['noSpeechProbability'] else None,
            'compression_ratio': float(x['compressionRatio']) if x.get('compressionRatio') else None,
            'segments': x.get('segments', []),
        })
    engine=ContextualStreamingCallerASR(fast, language if configured else None, context_ms, cadence_ms, 500)
    started=time.perf_counter(); chunk_ms=250
    for offset in range(0,duration,chunk_ms):
        end=min(duration,offset+chunk_ms); frame=pcm[offset*192:end*192]
        engine.ingest_caller(frame,offset,end); engine.drain_fast_once()
    engine.ingest_caller(b'\0'*(96_000),duration,duration+500)
    stable=engine.stable_fast; fields=semantic_fields(stable,language,required)
    useful=next((x['atMs'] for x in engine.metrics if all(semantic_fields(x.get('fastPartial',''),language,required).values())),None)
    stable_row=next((x for x in reversed(engine.metrics) if x['kind']=='FINAL'),{})
    return {'id':path.stem,'language':language,'variant':path.stem.rsplit('__',1)[-1],'expectedSemanticClass':klass,'sourceText':source,
      'languageMode':'configured' if configured else 'automatic','languageLock':{'language':engine.language.language,'confidence':engine.language.confidence,'locked':engine.language.locked},
      'fastRevisionTimeline':engine.metrics,'confirmedPrefixTimeline':engine.agreement.timeline,'stableFastTranscript':stable,'fastSemanticFields':fields,
      'negationPreserved':fields.get('negation') if 'negation' in required else None,'firstUsefulSemanticMs':useful,'stableFastAtMs':stable_row.get('atMs'),
      'endOfSpeechToFinalReadyMs':stable_row.get('endOfSpeechToFinalReadyMs'),'finalization':stable_row,'decodeSeconds':round(time.perf_counter()-started,3),'rtf':round((time.perf_counter()-started)/(duration/1000),3),
      'coalescedPartialJobs':engine.scheduler.coalesced,'maxPendingJobs':engine.scheduler.max_pending,'backlog':0,'pass':all(fields.values()),
      'failureReason':None if all(fields.values()) else 'missing semantic fields: '+', '.join(k for k,v in fields.items() if not v)}
def main():
    global MODEL_NAME, REQUESTED_COMPUTE_TYPE
    p=argparse.ArgumentParser(); p.add_argument('--benchmark',action='store_true'); p.add_argument('--automatic-only',action='store_true'); p.add_argument('--configured-only',action='store_true'); p.add_argument('--case-id',action='append',default=[]); p.add_argument('--experiment',default='finalizer_v2')
    p.add_argument('--model',choices=('tiny','base','small'),default=os.environ.get('SCUT_VALIDATION_MODEL','base'))
    p.add_argument('--device',choices=('cpu','cuda'),default=os.environ.get('SCUT_WHISPER_DEVICE','cpu'))
    p.add_argument('--compute-type',choices=('int8','float16'),default=None)
    a=p.parse_args()
    MODEL_NAME=a.model; REQUESTED_COMPUTE_TYPE=a.compute_type or ('float16' if a.device=='cuda' else 'int8')
    # Validation deliberately never has a CPU fallback: requested and resolved
    # values must be identical or the experiment is invalid.
    os.environ['SCUT_VALIDATION_MODEL']=MODEL_NAME; os.environ['SCUT_WHISPER_DEVICE']=a.device
    if a.device=='cuda' and REQUESTED_COMPUTE_TYPE!='float16': raise SystemExit('CUDA validation requires --compute-type float16 for this experiment.')
    if a.device=='cpu' and REQUESTED_COMPUTE_TYPE!='int8': raise SystemExit('CPU validation requires --compute-type int8 for this experiment.')
    files=sorted(FIXTURES.glob('*.wav'))
    if not files: raise SystemExit('Existing acoustic fixtures are missing; do not generate replacements here.')
    if a.automatic_only and a.configured_only: raise SystemExit('Choose at most one language-mode filter.')
    if a.case_id:
      wanted=set(a.case_id); files=[f for f in files if f.stem in wanted]
      missing=wanted-{f.stem for f in files}
      if missing: raise SystemExit('Unknown existing fixture IDs: '+', '.join(sorted(missing)))
    cuda_count=0
    if a.device=='cuda':
      try:
        import ctranslate2
        cuda_count=int(ctranslate2.get_cuda_device_count())
      except Exception as exc: raise SystemExit(f'CUDA validation preflight failed: {exc}')
      if cuda_count < 1: raise SystemExit('CUDA validation requested but no CUDA device is available; refusing CPU fallback.')
    # One actual inference must succeed before the case loop.  The cached model
    # is then reused by the subset/full validation, so this is both proof and
    # a fail-loud preflight rather than an alternate decode path.
    vram_before=gpu_memory_mib() if a.device=='cuda' else None
    proof_pcm,_=wav_to_guarded_pcm(files[0]); proof=transcribe_pcm_details(proof_pcm,vad_filter=False,model_name=MODEL_NAME,language=phrase_for(files[0])[0])
    vram_after=gpu_memory_mib() if a.device=='cuda' else None
    if not proof.get('text','').strip(): raise SystemExit('ASR validation preflight returned empty text; refusing to continue.')
    startup={'requestedModel':a.model,'requestedDevice':a.device,'requestedComputeType':REQUESTED_COMPUTE_TYPE,
             'resolvedModel':MODEL_NAME,'resolvedDevice':os.environ['SCUT_WHISPER_DEVICE'],'resolvedComputeType':REQUESTED_COMPUTE_TYPE,
             'cudaDeviceCount':cuda_count,'experiment':a.experiment,'selectedCaseCount':len(files),'preflightInferenceSucceeded':True,
             'gpuVramMiBBefore':vram_before,'gpuVramMiBAfter':vram_after,'gpuVramIncreased':None if vram_before is None or vram_after is None else vram_after>vram_before}
    if a.device=='cuda' and startup['gpuVramIncreased'] is not True: raise SystemExit('CUDA inference did not increase NVIDIA-reported VRAM; refusing to continue.')
    print(json.dumps({'startupConfig':startup},ensure_ascii=False),flush=True)
    configs=[(x,y) for x in (3000,4000,5000,6000) for y in (750,1000,1500)] if a.benchmark else [(6000,1000)]
    runs=[]
    for context,cadence in configs:
      for configured in ([False] if a.automatic_only else [True] if a.configured_only else [True,False]):
       cases=[run_case(f,configured,context,cadence) for f in files]
       runs.append({'contextMs':context,'cadenceMs':cadence,'languageMode':'configured' if configured else 'automatic','cases':cases,
        'semanticPreservationRate':sum(x['pass'] for x in cases)/len(cases),'negationFailures':sum(x['negationPreserved'] is False for x in cases),'coalescedJobs':sum(x['coalescedPartialJobs'] for x in cases)})
    device=os.environ.get('SCUT_WHISPER_DEVICE','cpu'); compute=REQUESTED_COMPUTE_TYPE
    safe_model=''.join(ch if ch.isalnum() else '_' for ch in MODEL_NAME); safe_experiment=''.join(ch if ch.isalnum() else '_' for ch in a.experiment)
    out=ROOT/'diagnostics'/f'{safe_model}_{device}_{compute}_{safe_experiment}_{time.strftime("%Y%m%d-%H%M%S")}.json'
    report={'historicalBaseline':{'path':'diagnostics/GPU_SMALL_CONTEXTUAL_ASR_VALIDATION_COMPLETED.json','sha256':'4F497A3B178B5D22D9F8AFC96F29013DDE9E76481CBFAB9ADD333E30427C6314','semanticPreservationRate':.5556,'cases':108},'startupConfig':startup,'model':MODEL_NAME,'device':device,'computeType':compute,'experiment':a.experiment,'architecture':'rolling caller FAST plus independent full-utterance endpoint candidate arbiter','runs':runs,'romanianStatus':'not acoustically validated; no local Romanian fixture voice'}
    write_report(report,out); print(json.dumps({'runs':len(runs),'output':str(out)},ensure_ascii=False));
if __name__=='__main__': main()
