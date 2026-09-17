"""Measure resident FAST base + ACCURATE small memory without concurrent ASR."""
import json
import os
from pathlib import Path
import psutil
from faster_whisper import WhisperModel

root=Path(__file__).resolve().parent.parent
def path(name):
    snapshots=root/'.local'/'models'/f'models--Systran--faster-whisper-{name}'/'snapshots'
    direct=root/'.local'/'models'/f'faster-whisper-{name}'
    return direct if (direct/'model.bin').is_file() else next(x for x in snapshots.iterdir() if (x/'model.bin').is_file())
p=psutil.Process(os.getpid()); before=p.memory_info().rss
fast=WhisperModel(str(path('base')),device='cpu',compute_type='int8')
accurate=WhisperModel(str(path('small')),device='cpu',compute_type='int8')
report={'fastModel':'base','accurateModel':'small','rssDeltaMiB':round((p.memory_info().rss-before)/1048576,1),'inferenceConcurrency':'serialized: models resident, never inferred concurrently'}
(root/'diagnostics'/'DUAL_PASS_ASR_RAM.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
