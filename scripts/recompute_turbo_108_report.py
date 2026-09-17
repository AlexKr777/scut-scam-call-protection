"""Recompute evaluator-only fields from the saved Turbo 108 transcript report."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
from backend.acoustic_validation import PHRASES, polarity_inversion, semantic_fields, write_report

SOURCE=ROOT/'diagnostics'/'large_v3_turbo_cuda_float16_108_20260906-195453.json'
def main():
    report=json.loads(SOURCE.read_text(encoding='utf-8'))
    for case in report['cases']:
        required=next(row[3] for row in PHRASES if row[:3]==(case['language'],case['expectedSemanticClass'],case['sourceText']))
        fields=semantic_fields(case['transcript'],case['language'],required)
        case['semanticFields']=fields; case['pass']=all(fields.values()); case['negationPreserved']=fields.get('negation')
        case['polarityInversion']=polarity_inversion(case['transcript'],case['language'],case['expectedSemanticClass'])
    cases=report['cases']; groups={kind:[x for x in cases if x['expectedSemanticClass']==kind] for kind in ('dangerous','protective','context')}
    failures=[{'id':x['id'],'sourceText':x['sourceText'],'transcript':x['transcript'],'reason':'missing semantic fields: '+', '.join(k for k,v in x['semanticFields'].items() if not v)} for x in cases if not x['pass']]
    report['summary']={'pass':sum(x['pass'] for x in cases),'total':len(cases), **{f'{k}Pass':sum(x['pass'] for x in v) for k,v in groups.items()}, **{f'{k}Total':len(v) for k,v in groups.items()}, 'negationPreserved':sum(x['negationPreserved'] is True for x in cases),'negationTotal':sum(x['negationPreserved'] is not None for x in cases),'polarityInversions':[x['id'] for x in cases if x['polarityInversion']],'remainingSemanticFailures':failures,'variantBreakdown':{variant:{'pass':sum(x['pass'] for x in cases if x['variant']==variant),'total':sum(x['variant']==variant for x in cases)} for variant in ('clean','mono16k','telephone','telephone_noise','low_level','compressed')}}
    report['correction']={'sourceReport':str(SOURCE),'inferencePerformed':False,'reason':'Recomputed polarity with backend.acoustic_validation.polarity_inversion and saved transcripts only.'}
    report['verdict']='TURBO_108_GOOD_ENOUGH' if report['summary']['pass']>62 and not report['summary']['polarityInversions'] else 'TURBO_108_NOT_GOOD_ENOUGH'
    out=ROOT/'diagnostics'/f'large_v3_turbo_cuda_float16_108_corrected_{time.strftime("%Y%m%d-%H%M%S")}.json'; write_report(report,out); print(out)
if __name__=='__main__': main()
