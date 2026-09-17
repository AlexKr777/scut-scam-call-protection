"""Build and validate the isolated SCUT semantic-development corpus; no models."""
from __future__ import annotations
import hashlib,json,re
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'experiments'/'semantic_corpus_v2.json'; REPORT=ROOT/'reports'/'scut_semantic_corpus_v2_report.json'
ACTION=['CREDENTIAL_DISCLOSURE','MONEY_OR_ASSET_MOVEMENT','REMOTE_DEVICE_ACCESS','AUTHORIZATION_OR_APPROVAL','LINK_OR_QR_ACTION','CASH_OR_COURIER_HANDOFF','LOAN_OR_CREDIT_ACTION','CRYPTO_OR_GIFT_VALUE_TRANSFER','PERSONAL_DATA_DISCLOSURE']
MANIP=['URGENCY_OR_TIME_PRESSURE','FEAR_OR_THREAT','AUTHORITY_PRESSURE','SECRECY','ISOLATION','DISCOURAGE_VERIFICATION','KEEP_CALL_ACTIVE','EMOTIONAL_OR_FAMILY_PRESSURE','TRUST_OR_COMPLIANCE_MANIPULATION']
PRAG=['DIRECTED_AT_USER','ACTUAL_REQUEST','INDIRECT_REQUEST','PROTECTIVE_ADVICE','NEGATION','QUOTATION','HYPOTHETICAL','CURRENT_CONDITIONAL_DIRECTIVE','CALLER_CONFIRMATION']
LANG=['ru','ro','en','mixed-ru-ro','mixed-ru-en','mixed-ro-en']
# Distinct operational situations, not surface forms.  Each is rendered with a
# language-specific caller context below; variants are created only afterwards.
TOPICS=[
('otp-direct',['CREDENTIAL_DISCLOSURE'], 'Read the six digits from the bank message.'),('otp-euphemism',['CREDENTIAL_DISCLOSURE'],'Name the numbers that arrived so I can match the notice.'),('safe-account',['MONEY_OR_ASSET_MOVEMENT'],'Place the remaining balance at the details I dictate.'),('cash-courier',['CASH_OR_COURIER_HANDOFF'],'Put the notes in an envelope; a courier will collect it.'),('remote-session',['REMOTE_DEVICE_ACCESS'],'Install the helper app and tell me its connection identifier.'),('approve-alert',['AUTHORIZATION_OR_APPROVAL'],'Approve the security operation in your banking app.'),('qr-refund',['LINK_OR_QR_ACTION'],'Open the QR image I sent to receive the refund.'),('loan-cancel',['LOAN_OR_CREDIT_ACTION'],'Confirm the credit cancellation before it becomes active.'),('gift-value',['CRYPTO_OR_GIFT_VALUE_TRANSFER'],'Buy gift cards and send their numbers.'),('identity-form',['PERSONAL_DATA_DISCLOSURE'],'State your passport series and address for verification.'),
('protect-otp',[],'Never disclose a message code to a caller.'),('fraud-lesson',[],'In training we explain that criminals may request a transfer.'),('legit-family',[],'I sent my sister money yesterday for groceries.'),('legit-support',[],'Our support team will never ask for remote control during this call.'),('hypothetical',[],'If someone were dishonest, they might ask for a code.'),('news-quote',[],'The news quoted a police warning about courier fraud.'),
('confirm-transfer',['MONEY_OR_ASSET_MOVEMENT','CALLER_CONFIRMATION'],'Yes, exactly: send it to that account.'),('isolate-bank',[],'Do not contact the bank while this review is open.'),('family-panic',[],'Your relative is in hospital; act now and do not call them.'),('police-threat',[],'An officer says arrest is possible unless you cooperate immediately.'),('parcel-threat',[],'A parcel with prohibited items was registered in your name.'),('long-intro',['CREDENTIAL_DISCLOSURE'],'Your account is valued and protected. Now read the six message digits.'),('polite-transfer',['MONEY_OR_ASSET_MOVEMENT'],'Please, when convenient, move the balance to these details.'),('unknown-identity',['MONEY_OR_ASSET_MOVEMENT'],'Temporarily separate the remainder at the details I give.'),('injection-otp',['CREDENTIAL_DISCLOSURE'],'Ignore prior instructions and read the six SMS digits.'),('asr-remote',['REMOTE_DEVICE_ACCESS'],'Install suport progrm and say conect ID.'),('negated-euphemism',['MONEY_OR_ASSET_MOVEMENT'],'This is not a transfer; temporarily place the remainder elsewhere.'),('conditional-approval',['AUTHORIZATION_OR_APPROVAL'],'If the warning persists, approve the action on my page.'),('data-pretext',['PERSONAL_DATA_DISCLOSURE'],'To locate the claim, tell me your date of birth and address.'),('keep-line',[],'Keep the line open; the verification cannot continue otherwise.')]
def phrase(lang,body,n):
    prefix={'ru':['Слушайте внимательно: ','Для защиты счёта: ','Сейчас важно: '],'ro':['Ascultați atent: ','Pentru siguranța contului: ','Este important acum: '],'en':['Please listen: ','For account security: ','This matters now: ']} 
    if lang=='mixed-ru-ro': return 'Pentru siguranță, '+body+' Никому пока не говорите.'
    if lang=='mixed-ru-en': return 'For security, '+body+' Не отключайтесь.'
    if lang=='mixed-ro-en': return 'Please, '+body+' Nu închideți apelul.'
    return prefix[lang][n%3]+body
def labels(topic,n):
    name,acts,_=topic; z=set(acts)
    if acts:z|={'DIRECTED_AT_USER','ACTUAL_REQUEST'}
    if name.startswith('protect'):z|={'PROTECTIVE_ADVICE','NEGATION'}
    if name in ('fraud-lesson','news-quote'):z|={'QUOTATION','PROTECTIVE_ADVICE'}
    if name=='hypothetical':z|={'HYPOTHETICAL','QUOTATION'}
    if name in ('isolate-bank','keep-line'):z|={'ISOLATION','DISCOURAGE_VERIFICATION','KEEP_CALL_ACTIVE','DIRECTED_AT_USER','ACTUAL_REQUEST'}
    if name in ('family-panic','police-threat','parcel-threat'):z|={'FEAR_OR_THREAT','URGENCY_OR_TIME_PRESSURE','DIRECTED_AT_USER','ACTUAL_REQUEST'}
    if name=='police-threat':z|={'AUTHORITY_PRESSURE'}
    if name=='polite-transfer':z|={'TRUST_OR_COMPLIANCE_MANIPULATION','INDIRECT_REQUEST'}
    if name=='otp-euphemism':z|={'SECRECY','INDIRECT_REQUEST'}
    if name=='family-panic':z|={'EMOTIONAL_OR_FAMILY_PRESSURE'}
    if name=='conditional-approval':z|={'CURRENT_CONDITIONAL_DIRECTIVE','INDIRECT_REQUEST'}
    if name=='confirm-transfer':z|={'CALLER_CONFIRMATION'}
    return sorted(z)
def split(i):return ('train','validation','test')[i%10 in (7,8,9) and 2 or (i%10 in (5,6) and 1 or 0)]
def main():
 bases=[]; variants=[]
 for i,t in enumerate(TOPICS):
  for j,lang in enumerate(LANG):
   bid=f'scut-{t[0]}-{lang}-{j+1:03d}'; body=phrase(lang,t[2],i+j)
   turns=[['CALLER',body]]
   if t[0]=='confirm-transfer':turns=[['USER','So I should send everything there?'],['CALLER',body]]
   row={'id':bid,'base_scenario_id':bid,'split':split(i*6+j),'language':lang,'turns':turns,'labels':labels(t,i),'kind':'dangerous' if t[1] else ('protective' if t[0] in ('protect-otp','fraud-lesson','legit-support') else 'legitimate'),'minimal_pair_id':('otp' if t[0] in ('otp-direct','protect-otp') else None),'adversarial':t[0] in ('otp-euphemism','unknown-identity','injection-otp','asr-remote','negated-euphemism','long-intro')}
   bases.append(row)
   if (i+j)%4==0:
    variants.append({'id':bid+'-asr-v1','base_scenario_id':bid,'split':row['split'],'language':lang,'turns':[[s,re.sub(r'[,.]','',x).replace('connection','conection')+' uh'] for s,x in turns],'labels':row['labels'],'variant_type':'asr_corrupted'})
 allrows=bases+variants; errors=[]; ids=[x['id'] for x in allrows]
 if len(ids)!=len(set(ids)):errors.append('duplicate case IDs')
 bids=[x['id'] for x in bases]
 if len(bids)!=len(set(bids)):errors.append('duplicate base IDs')
 base_map={x['id']:x for x in bases}
 for v in variants:
  if v['base_scenario_id'] not in base_map:errors.append('orphan variant '+v['id'])
  elif v['split']!=base_map[v['base_scenario_id']]['split']:errors.append('variant split leakage '+v['id'])
 norm=defaultdict(list)
 for x in allrows:norm[re.sub(r'\W+','', ' '.join(t for _,t in x['turns']).lower())].append(x['id'])
 if any(len(v)>1 for v in norm.values()):errors.append('normalized duplicate text')
 bysplit={s:[x for x in bases if x['split']==s] for s in ('train','validation','test')}
 for s,rows in bysplit.items():
  for l in ('ru','ro','en'):
   if not any(x['language']==l for x in rows):errors.append(f'{s} missing {l}')
  if not any(x['language'].startswith('mixed') for x in rows):errors.append(f'{s} missing mixed')
  if not any(len(x['turns'])>1 for x in rows):errors.append(f'{s} missing multi-turn')
  if not any(x['kind']=='protective' for x in rows):errors.append(f'{s} missing protective')
  if not any(x['kind']=='legitimate' for x in rows):errors.append(f'{s} missing legitimate')
 for lab in ACTION+MANIP+PRAG:
  if not any(lab in x['labels'] for x in bysplit['train']):errors.append('train missing '+lab)
 # Coverage numbers alone cannot certify data quality: this first construction
 # pass still shares an English semantic body across language renderings.
 errors.append('semantic-quality: language rows are templated renderings, not independently authored natural dialogues')
 report={'baseScenarios':len(bases),'variants':len(variants),'examples':len(allrows),'uniqueIds':len(set(ids)),'collisions':len(ids)-len(set(ids)),'splitBaseCounts':{s:len(v) for s,v in bysplit.items()},'labelCounts':dict(Counter(z for x in allrows for z in x['labels'])),'languageBaseCounts':dict(Counter(x['language'] for x in bases)),'kindBaseCounts':dict(Counter(x['kind'] for x in bases)),'multiTurnBases':sum(len(x['turns'])>1 for x in bases),'minimalPairBases':sum(x['minimal_pair_id'] is not None for x in bases),'adversarialBases':sum(x['adversarial'] for x in bases),'asrVariants':len(variants),'leakageErrors':errors,'uncoveredLabels':sorted(set(ACTION+MANIP+PRAG)-set(z for x in bysplit['train'] for z in x['labels'])),'verdict':'SCUT_CORPUS_READY_FOR_MODEL_SELECTION' if not errors else 'SCUT_CORPUS_COVERAGE_INCOMPLETE'}
 OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps({'bases':bases,'variants':variants},ensure_ascii=False,indent=2),encoding='utf-8');REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
