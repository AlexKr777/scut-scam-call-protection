"""Attach the selected base+small resident memory evidence to the benchmark."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent.parent
benchmark=root/'diagnostics'/'DUAL_PASS_ASR_BENCHMARK.json'
ram=root/'diagnostics'/'DUAL_PASS_ASR_RAM.json'
value=json.loads(benchmark.read_text(encoding='utf8'))
value['residentModels']=json.loads(ram.read_text(encoding='utf8'))
benchmark.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
