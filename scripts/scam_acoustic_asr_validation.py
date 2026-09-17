"""Generate offline SAPI fixtures (when voices exist) and run acoustic FAST validation.

Run: python scripts/scam_acoustic_asr_validation.py
Fixtures are diagnostics-only.  If a language voice/model is absent, the JSON
states that plainly; it never substitutes source text for acoustic evidence.
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from backend.acoustic_validation import PHRASES, make_degraded_pcm, report_case, write_wav, write_report
from backend.guarded_audio import transcribe_pcm_details
from backend.dual_pass_asr import ASRText

OUT=ROOT/'diagnostics'/'tests'/'scam_acoustic_fixtures'; REPORT=ROOT/'diagnostics'/'SCAM_ACOUSTIC_ASR_VALIDATION.json'
VARIANTS=('clean','mono16k','telephone','telephone_noise','low_level','compressed')
VOICE_CULTURE={'ru':'ru-ru','en':'en-us','ro':'ro-ro'}

def sapi_voices() -> set[str]:
    command="Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.GetInstalledVoices() | % {$_.VoiceInfo.Culture.Name}"
    result=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,encoding='utf-8')
    return {item.strip().lower() for item in result.stdout.splitlines() if item.strip()}

def synthesize(text: str, language: str, target: Path) -> bool:
    # Text is transported as a UTF-8 file, avoiding PowerShell command-line encoding loss.
    target.parent.mkdir(parents=True, exist_ok=True)
    source=target.with_suffix('.txt'); source.write_text(text,encoding='utf-8')
    ps="""param($sourcePath,$outputPath,$culture)
Add-Type -AssemblyName System.Speech
$text=[IO.File]::ReadAllText($sourcePath,[Text.Encoding]::UTF8)
$s=New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice=$s.GetInstalledVoices() | ? {$_.VoiceInfo.Culture.Name -eq $culture} | Select -First 1
if($null -eq $voice){exit 7}; $s.SelectVoice($voice.VoiceInfo.Name); $s.SetOutputToWaveFile($outputPath); $s.Speak($text); $s.Dispose()
"""
    runner=target.with_suffix('.ps1'); runner.write_text(ps,encoding='utf-8')
    result=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(runner),str(source),str(target),language],capture_output=True,text=True,encoding='utf-8')
    source.unlink(missing_ok=True); runner.unlink(missing_ok=True)
    return result.returncode == 0 and target.exists()

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--fixtures-only',action='store_true'); args=parser.parse_args()
    voices=sapi_voices(); generated=[]; unavailable=[]
    for number,(language, klass, text, _) in enumerate(PHRASES, 1):
        clean=OUT/f'{number:02d}_{language}_{klass}__clean.wav'
        culture=VOICE_CULTURE[language]
        if culture not in voices:
            unavailable.append({'language':language,'text':text,'reason':'no local offline SAPI voice'}); continue
        if not clean.exists() and not synthesize(text, culture, clean):
            unavailable.append({'language':language,'text':text,'reason':'SAPI synthesis failed'}); continue
        from backend.acoustic_validation import wav_to_guarded_pcm
        pcm, _=wav_to_guarded_pcm(clean)
        for variant in VARIANTS:
            raw,rate,channels=make_degraded_pcm(pcm,variant)
            path=OUT/f'{number:02d}_{language}_{klass}__{variant}.wav'; write_wav(path,raw,rate,channels); generated.append((language,klass,text,path))
    if args.fixtures_only:
        print(json.dumps({'generated':len(generated),'unavailable':unavailable},ensure_ascii=False)); return 0
    def fast(raw): return transcribe_pcm_details(raw,vad_filter=False,model_name='base')['text']
    def accurate(raw):
        x=transcribe_pcm_details(raw,vad_filter=False,model_name='small'); return ASRText(x['text'],x['language'],float(x['languageProbability']))
    cases=[]; model_error=None
    try:
        for n,(language,klass,text,path) in enumerate(generated,1):
            cases.append(report_case(f'acoustic-{n:03d}',language,klass,text,path,fast,accurate))
    except RuntimeError as error: model_error=str(error)
    summary={'testedCases':len(cases),'coverage':{lang:sum(c['language']==lang for c in cases) for lang in ('ru','ro','en')},
             'fastSemanticPreservationRate':round(sum(c['pass'] for c in cases)/len(cases),3) if cases else None,
             'readyForSemanticClassification': bool(cases) and not model_error and all(c['pass'] for c in cases),
             'limitation': model_error, 'unavailableAcousticCoverage':unavailable}
    report={'schemaVersion':1,'fastConfig':{'model':'faster-whisper-base','computeType':'int8','windowSeconds':2,'strideSeconds':1,'callerPath':'DualChannelPipeline'},'summary':summary,'cases':cases}
    write_report(report,REPORT); print(json.dumps(summary,ensure_ascii=False,indent=2)); return 0 if not model_error else 2
if __name__=='__main__': raise SystemExit(main())
