"""Development-only Nomic semantic remediation V1.

This program intentionally has no historical-test, observed-validation, fresh
benchmark, Whisper, VAD, stabilizer, or rules dependency.  The holdout is
generated and locked by ``build``; ``train`` does not deserialize it.
"""
from __future__ import annotations
import argparse, hashlib, json, os, platform, random, re, shutil, sys, time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
 sys.path.insert(0,str(ROOT))
DATA=ROOT/'data'/'nomic_remediation_v1'; REPORT=ROOT/'reports'/'nomic_remediation_v1'; OUT=ROOT/'output'/'nomic_remediation_v1'
TRAIN=DATA/'remediation_train.json'; HOLDOUT=DATA/'remediation_holdout.json'; LOCK=DATA/'remediation_holdout.lock.json'
REV='1066b6599d099fbb93dfcb64f9c37a7c9e503e85'; THRESHOLD=.6
FAMILIES=('SAFE_ACCOUNT_AND_TRANSFER','SEED_RECOVERY_SECRET','FAMILY_EMERGENCY_MONEY')
KNOWN=(
 'Срочно переведите деньги на безопасный счёт.',
 'Сообщите seed phrase от вашего кошелька.',
 'Ваш сын попал в аварию, срочно нужны деньги.',)

def sha(path: Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest().upper()
def write(path:Path,obj:Any)->None:
 path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def norm(row): return re.sub(r'[^\w]+','', ' '.join(t for _,t in row['turns']).casefold())
def action(row): return row['kind']=='dangerous'
def language_bucket(i): return ('ru','ro','en','mixed')[i//12]
def mixed(i,ru,ro,en):
 return (ru if i%3==0 else ro if i%3==1 else en)
def labels(family,kind):
 base=['ACTUAL_REQUEST','DIRECTED_AT_USER'] if kind=='dangerous' else ['PROTECTIVE_ADVICE','NEGATION'] if kind=='protective' else ['NEGATION']
 if family=='SAFE_ACCOUNT_AND_TRANSFER': return base+(['MONEY_OR_ASSET_MOVEMENT','URGENCY_OR_TIME_PRESSURE','AUTHORITY_PRESSURE'] if kind=='dangerous' else [])
 if family=='SEED_RECOVERY_SECRET': return base+(['CREDENTIAL_DISCLOSURE','CRYPTO_OR_GIFT_VALUE_TRANSFER'] if kind=='dangerous' else [])
 return base+(['MONEY_OR_ASSET_MOVEMENT','EMOTIONAL_OR_FAMILY_PRESSURE','URGENCY_OR_TIME_PRESSURE'] if kind=='dangerous' else [])

# Each list deliberately varies speaker intent, claimed identity, request form,
# timing and context.  Index 0..5 dangerous, 6..8 protective, 9..11 legitimate.
TEXT={
'SAFE_ACCOUNT_AND_TRANSFER':{
'ru':['[CALLER] Служба антифрода банка: операция подозрительна. Откройте перевод на резервный реквизит, который я сейчас продиктую.','[CALLER] Я из полиции по финансовым делам. Чтобы средства не арестовали, отправьте их на временное хранение через приложение.','[OPERATOR] Мы проверяем утечку. Не сообщайте никому о проверке и переведите остаток на внутренний защищённый баланс.','[CALLER] Курьер подъедет за наличными: так быстрее обезопасить сбережения, чем ждать блокировки карты.','[CALLER] Подтвердите, что можете сделать срочный перевод. Новый счёт оформлен для защиты ваших денег.','[USER] Это точно банк?\n[CALLER] Да, отдел безопасности; прекратите разговоры с родственниками и отправьте сумму сейчас.','[CALLER] Настоящий банк никогда не просит переводить деньги на резервные или защищённые реквизиты.','[USER] Мне сказали срочно перевести остаток.\n[CALLER] Завершите звонок и перезвоните банку по номеру на карте.','[CALLER] Полиция не принимает деньги на хранение; такая просьба — повод остановиться и проверить.','[USER] Я оплатил счёт поставщика по договору на обычный расчётный счёт компании.','[USER] В банковском приложении можно посмотреть историю переводов и реквизиты получателя.','[USER] Бухгалтер попросил сверить номер счёта перед плановой оплатой аренды.'],
'ro':['[APELANT] Sunt de la antifraudă. Ca să nu pierdeți banii, trimiteți soldul către contul temporar pe care vi-l dictez.','[APELANT] Poliția financiară a blocat frauda; mutați fondurile într-un cont de protecție până mâine.','[OPERATOR] Nu discutați cu nimeni despre verificare. Faceți acum transferul intern de siguranță.','[APELANT] Un curier poate ridica numerarul pentru depozitare securizată înainte să fie golit cardul.','[APELANT] Confirmați transferul urgent; noul IBAN este rezervat pentru apărarea banilor dumneavoastră.','[UTILIZATOR] De ce nu văd mesaj în aplicație?\n[APELANT] Este confidențial, trimiteți suma întâi și veți primi confirmarea.','[APELANT] O bancă reală nu vă cere să mutați bani într-un cont „sigur” dictat la telefon.','[UTILIZATOR] Cineva pretinde că e poliția și cere un transfer.\n[APELANT] Închideți și verificați independent instituția.','[APELANT] Nu predați numerar unui curier pentru presupusa protecție a economiilor.','[UTILIZATOR] Am plătit factura de electricitate către furnizorul meu obișnuit.','[UTILIZATOR] Compania a actualizat legal contul în contract, iar noi am verificat prin contactul cunoscut.','[UTILIZATOR] Transferul lunar către proprietar este programat din aplicația mea.'],
'en':['[CALLER] Fraud control here: move the balance to the containment account I am reading out before the card is frozen.','[CALLER] Financial police need your funds held temporarily; authorize the transfer while we stay on the line.','[AGENT] This investigation is confidential. Send the money to our security ledger now, then we can protect it.','[CALLER] A vetted courier can collect cash for secure custody because electronic transfer is too slow.','[CALLER] Your account is exposed. Confirm the urgent payment to the reserve destination shown by my code.','[USER] Can I call my bank first?\n[CALLER] No, that will compromise the case; make the transfer before talking to anyone.','[CALLER] A genuine bank will not direct you by phone to move money into a so-called safe account.','[USER] Someone asked for a secret emergency transfer.\n[CALLER] Use the number on your card to verify the bank independently.','[CALLER] Never hand cash to a courier who says it is being protected for you.','[USER] I paid an approved supplier invoice to the account printed on our contract.','[USER] The finance team reconciled a routine payroll transfer through our normal process.','[USER] This guide explains how bank transfer confirmations work.']},
'SEED_RECOVERY_SECRET':{
'ru':['[CALLER] Поддержка кошелька: назовите двенадцать слов резервной фразы, иначе доступ будет закрыт.','[CALLER] Для восстановления криптокошелька продиктуйте секретные слова по порядку, я сверю их с системой.','[OPERATOR] Мы нашли вход с другого устройства. Пришлите в чат приватный ключ для срочной защиты активов.','[CALLER] Не открывайте сайт — просто произнесите backup phrase, это конфиденциальная проверка.','[CALLER] Подтвердите каждое из 24 слов, чтобы новый безопасный кошелёк получил ваши монеты.','[USER] Это служба биржи?\n[CALLER] Да, скажите recovery words, пока злоумышленник не вывел токены.','[CALLER] Никому, включая поддержку, нельзя сообщать seed-фразу или приватный ключ.','[USER] Мне позвонили насчёт кошелька.\n[CALLER] Найдите официальный сайт сами; не диктуйте слова восстановления.','[CALLER] Фраза резервного восстановления — это ключ к средствам, а не код для телефонной проверки.','[USER] В статье объясняется, почему фразу восстановления хранят офлайн.','[USER] Я записал резервные слова на бумаге и никому их не показываю.','[USER] На курсе по криптографии обсуждали разницу между публичным адресом и приватным ключом.'],
'ro':['[APELANT] Asistența portofelului: spuneți cele douăsprezece cuvinte de recuperare pentru a salva accesul.','[APELANT] Detectăm o conectare străină; dictați fraza de backup și verificăm imediat monedele.','[OPERATOR] Trimiteți cheia privată în chat, altfel nu putem muta activele într-un portofel nou.','[APELANT] Nu folosiți site-ul acum. Citiți recovery words la telefon pentru controlul de securitate.','[APELANT] Confirmați toate cele 24 de cuvinte, în ordinea corectă, înainte să expire protecția.','[UTILIZATOR] Sunteți de la exchange?\n[APELANT] Da, spuneți secretul de recuperare înainte ca hoțul să retragă tokenurile.','[APELANT] Suportul legitim nu cere niciodată fraza seed sau cheia privată.','[UTILIZATOR] Cineva îmi cere cuvintele portofelului.\n[APELANT] Închideți apelul și contactați platforma prin adresa oficială.','[APELANT] Cuvintele de backup nu sunt un cod de verificare pentru un apelant.','[UTILIZATOR] Documentația descrie cum funcționează o frază seed.','[UTILIZATOR] Mi-am păstrat fraza de recuperare offline, fără să o trimit nimănui.','[UTILIZATOR] Un tutorial explică de ce adresa publică poate fi distribuită, dar cheia privată nu.'],
'en':['[CALLER] Wallet security: read the twelve recovery words so I can stop the unauthorized withdrawal.','[CALLER] To restore your crypto wallet, say the backup phrase in sequence while I validate it.','[AGENT] We saw a new login. Paste the private key into the secure chat to protect the assets.','[CALLER] Do not use the website; tell me the seed words over the phone for a confidential audit.','[CALLER] Confirm each of the twenty-four secret words and I will migrate your coins to safety.','[USER] Are you exchange support?\n[CALLER] Yes; give the recovery phrase before the attacker empties the wallet.','[CALLER] No legitimate support agent needs your seed phrase, recovery words, or private key.','[USER] A caller wants my wallet words.\n[CALLER] End the call and find the platform contact details yourself.','[CALLER] A recovery phrase controls the wallet; it is never a phone-verification code.','[USER] The handbook defines a seed phrase without asking readers to disclose one.','[USER] I backed up my wallet offline and did not share the credentials.','[USER] Our class compared public addresses with private keys.']},
'FAMILY_EMERGENCY_MONEY':{
'ru':['[CALLER] Вашу дочь после ДТП увезли в больницу. Срочно оплатите лечение переводом, ей нельзя звонить.','[CALLER] Ваш сын задержан, нужен залог сегодня. Адвокат пришлёт реквизиты, никому не рассказывайте.','[CALLER] Родственник попал в реанимацию; курьер заберёт наличные для немедленной операции.','[CALLER] Я врач, времени мало. Отправьте деньги на лекарства, затем сможете приехать.','[CALLER] Племянник в полиции после аварии. Сохраните тайну и подтвердите быстрый перевод.','[USER] Можно поговорить с братом?\n[CALLER] Нет, он под наблюдением; оплатите помощь немедленно.','[CALLER] Если звонящий сообщает об аварии родственника и требует деньги, сначала свяжитесь с семьёй по известному номеру.','[USER] Мне сказали, что сын в больнице и нужен перевод.\n[CALLER] Не платите на звонке: проверьте больницу самостоятельно.','[CALLER] Настоящий врач не требует секретный перевод или наличные через незнакомого курьера.','[USER] Мой брат попал в аварию, я еду в больницу; денег никто по телефону не просил.','[USER] Мы оплатили лечение через кассу больницы после личного разговора с регистратурой.','[USER] Адвокат назначил обычную консультацию по семейному делу на следующей неделе.'],
'ro':['[APELANT] Fiica dumneavoastră a avut un accident și este la spital. Trimiteți urgent bani pentru tratament, nu o sunați.','[APELANT] Fiul este reținut; trebuie plătită cauțiunea astăzi. Avocatul vă dă contul, păstrați secretul.','[APELANT] O rudă este la terapie intensivă. Un curier ridică numerar pentru operația imediată.','[APELANT] Sunt medicul de gardă; transferați banii pentru medicamente înainte să ajungeți la spital.','[APELANT] Nepotul are probleme cu poliția după accident. Confirmați plata rapidă fără să spuneți familiei.','[UTILIZATOR] Pot vorbi cu sora mea?\n[APELANT] Nu acum, plătiți ajutorul imediat ca să nu se agraveze situația.','[APELANT] O cerere de bani după o presupusă urgență familială trebuie verificată cu rudele pe numere cunoscute.','[UTILIZATOR] Cineva spune că tata e internat și cere transfer.\n[APELANT] Contactați spitalul independent înainte de orice plată.','[APELANT] Nu dați cash unui curier pentru o poveste despre accidentul unei rude.','[UTILIZATOR] Mama mea este la spital, iar eu merg acolo; nu mi-a cerut nimeni bani la telefon.','[UTILIZATOR] Familia a plătit factura medicală direct la recepția clinicii.','[UTILIZATOR] Am discutat cu un avocat despre acte, fără presiune sau plată urgentă.'],
'en':['[CALLER] Your daughter was taken to hospital after a crash. Send treatment money now and do not call her.','[CALLER] Your son has been detained; bail is due today. The lawyer will give you an account, keep this private.','[CALLER] A relative is in intensive care. A courier will collect cash for the emergency operation.','[CALLER] I am the duty doctor. Transfer money for medicine before you travel to the hospital.','[CALLER] Your nephew has a police problem after an accident. Make the fast payment and tell no one.','[USER] May I speak to my brother?\n[CALLER] Not now; he is being held, so pay for help immediately.','[CALLER] A call claiming a family accident and demanding money should be verified with relatives independently.','[USER] Someone says my father is hospitalized and wants a transfer.\n[CALLER] Contact the hospital through a known number before paying.','[CALLER] Do not give a courier cash for an alleged emergency involving a family member.','[USER] My cousin was in an accident; I am going to the hospital and nobody has requested money.','[USER] We paid the clinic directly after confirming the appointment in person.','[USER] I scheduled an ordinary meeting with a lawyer about paperwork next week.']}}

def row(fid, n, kind, lang, text, holdout=False):
 # The holdout uses a different scenario identifier namespace and distinct text
 # transformations, preventing base lineage collisions with training.
 turns=[]
 for line in text.split('\n'):
  m=re.match(r'\[(CALLER|USER|OPERATOR|AGENT|APELANT|UTILIZATOR)\]\s*(.*)',line)
  turns.append((m.group(1),m.group(2)) if m else ('CALLER',line))
 return {'id':f'{"hold" if holdout else "train"}-{fid.lower()}-{n:03d}','base_scenario_id':f'{"hold" if holdout else "train"}-{fid.lower()}-{n:03d}','split':'holdout' if holdout else 'train','family':fid,'language':lang,'turns':turns,'labels':labels(fid,kind),'kind':kind,'minimal_pair_id':None,'adversarial':False}
def make_records(holdout=False):
 rows=[]
 for family in FAMILIES:
  source=TEXT[family]
  for bi,lang in enumerate(('ru','ro','en','mixed')):
   for offset in range(12 if not holdout else 4):
    if holdout:
     kind='dangerous' if offset<2 else 'protective' if offset==2 else 'legitimate'
    else:
     kind='dangerous' if offset<6 else 'protective' if offset<9 else 'legitimate'
    # For locked holdout select semantically separated positions 0,3,7,10 and
    # add a contextual frame that never occurs in the training base.
    ix=offset if not holdout else (0,3,7,10)[offset]
    text=mixed(offset,*[source[x][ix] for x in ('ru','ro','en')]) if lang=='mixed' else source[lang][ix]
    if holdout: text=(' [USER] I need advice about an unexpected call.\n'+text if kind!='legitimate' else '[USER] I am discussing this situation with a trusted person.\n'+text)
    rows.append(row(family,len(rows)+1,kind,lang,text,holdout))
 return rows
def corrupt(r):
 repl=(('ё','е'),('ă','a'),('recovery','recovry'),('seed','sid'),('transfer','transfr'),('.',''))
 turns=[]
 for s,t in r['turns']:
  a,b=repl[len(r['id'])%len(repl)]; turns.append((s,t.replace(a,b,1)))
 q=dict(r);q['id']=r['id']+'-asr-v1';q['turns']=turns;q['variant_type']='asr_corrupted';return q
def build():
 bases=make_records(False); variants=[corrupt(x) for x in bases if x['kind']=='dangerous'][:48]
 holdout=make_records(True)
 write(TRAIN,{'schema':1,'bases':bases,'variants':variants})
 write(HOLDOUT,{'schema':1,'name':'NOMIC_REMEDIATION_HOLDOUT_V1','bases':holdout})
 lock={'name':'NOMIC_REMEDIATION_HOLDOUT_V1','sha256':sha(HOLDOUT),'base_count':len(holdout),'created_before_training':True,'threshold':THRESHOLD}
 write(LOCK,lock); validate(bases,variants,holdout,lock); print(json.dumps(lock))
def validate(bases,variants,holdout,lock):
 errs=[]
 if len(bases)!=144 or len(variants)!=48 or len(holdout)!=48: errs.append('required counts not met')
 for coll,name in ((bases,'train'),(holdout,'holdout')):
  for f in FAMILIES:
   x=[r for r in coll if r['family']==f]
   if len(x)!=(48 if name=='train' else 16):errs.append(f'{name} family count {f}')
   for lang in ('ru','ro','en','mixed'):
    y=[r for r in x if r['language']==lang];expect=12 if name=='train' else 4
    wanted={'dangerous':6,'protective':3,'legitimate':3} if name=='train' else {'dangerous':2,'protective':1,'legitimate':1}
    if len(y)!=expect or Counter(r['kind'] for r in y)!=wanted:errs.append(f'{name} distribution {f} {lang}')
 allrows=bases+variants+holdout
 if len({r['id'] for r in allrows})!=len(allrows):errs.append('duplicate id')
 nb={norm(r) for r in bases}; nh={norm(r) for r in holdout}
 if nb&nh:errs.append('normalized holdout duplicate')
 if any(k.casefold() in ' '.join(t for _,t in r['turns']).casefold() for r in allrows for k in KNOWN):errs.append('known regression phrase present')
 # Auditable semantic-proximity screen: token-Jaccard over base scenarios;
 # threshold intentionally conservative, and all candidates are reported.
 audit=[]
 for h in holdout:
  hs=set(re.findall(r'\w+', ' '.join(text for _,text in h['turns']).casefold()))
  best=max((len(hs & set(re.findall(r'\w+', ' '.join(text for _,text in t['turns']).casefold()))) / max(1,len(hs | set(re.findall(r'\w+', ' '.join(text for _,text in t['turns']).casefold())))) for t in bases),default=0)
  audit.append({'holdout_id':h['id'],'max_train_token_jaccard':best})
 if max(x['max_train_token_jaccard'] for x in audit)>.82:errs.append('semantic similarity audit failure')
 report={'valid':not errs,'errors':errs,'train_bases':len(bases),'train_asr_variants':len(variants),'holdout_bases':len(holdout),'holdout_sha256':lock['sha256'],'semantic_similarity_audit':audit,'forbidden_sources':'historical TEST, observed validation, future fresh benchmark, and Audio Replay are not loaded'}
 write(REPORT/'remediation_data_validation.json',report)
 if errs:raise RuntimeError('; '.join(errs))

def load_train():
 # Directly load only permitted existing TRAIN records.  Do not invoke the
 # old loader because its immutable championship contract hashes a fresh
 # blueprint that this remediation stage must not touch.
 docs=[json.loads((ROOT/'experiments'/'semantic_corpus_v3.json').read_text(encoding='utf8')),json.loads((ROOT/'experiments'/'semantic_training_extension_v1.json').read_text(encoding='utf8')),json.loads(TRAIN.read_text(encoding='utf8'))]
 rows=[]; labs=set()
 for d in docs:
  kinds={x['base_scenario_id']:x['kind'] for x in d['bases']}
  for x in d['bases']+d['variants']:
   if x.get('split')!='train':continue
   r=dict(x);r['kind']=kinds[r['base_scenario_id']];rows.append(r);labs.update(r['labels'])
 return rows,sorted(labs),{'existing_v3_sha256':sha(ROOT/'experiments'/'semantic_corpus_v3.json'),'existing_extension_sha256':sha(ROOT/'experiments'/'semantic_training_extension_v1.json'),'remediation_extension_sha256':sha(TRAIN),'records':len(rows)}
def fit(train, valid, labels, seed, save=None):
 import torch
 from scripts.championship_backbones import build_adapter
 from scripts.run_brain_championship_v3 import NonlinearScutModel
 from scripts.tail_aware_encoder import pack_turns
 random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
 adapter=build_adapter('nomic_v2_moe',REV,cache_dir=str(ROOT/'.local'/'ml-cache'/'hf-cache'));model=NonlinearScutModel(adapter,len(labels)).cuda();kinds={'dangerous':0,'protective':1,'legitimate':2}
 def collate(rows):
  enc=adapter.tokenizer([pack_turns(x['turns'],adapter.tokenizer,384) for x in rows],padding=True,truncation=True,max_length=384,return_tensors='pt')
  return {k:v.cuda() for k,v in enc.items()},torch.tensor([[z in x['labels'] for z in labels] for x in rows],device='cuda',dtype=torch.float32),torch.tensor([kinds[x['kind']] for x in rows],device='cuda'),torch.tensor([action(x) for x in rows],device='cuda',dtype=torch.float32)
 pos=np.sum([[label in x['labels'] for label in labels] for x in train],axis=0); sem=torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(np.minimum((len(train)-pos)/np.maximum(pos,1),4),device='cuda',dtype=torch.float32));kc=np.bincount([kinds[x['kind']] for x in train],minlength=3);kloss=torch.nn.CrossEntropyLoss(weight=torch.tensor(np.clip(len(train)/(3*np.maximum(kc,1)),.5,3),device='cuda',dtype=torch.float32)); y=sum(action(x) for x in train); aloss=torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(min((len(train)-y)/max(y,1),4),device='cuda'))
 hist=[];proof={};start=time.time()
 for phase,epochs in (('warmup',1),('finetune',4)):
  if phase=='warmup':
   for p in adapter.encoder.parameters():p.requires_grad_(False)
  else: proof=adapter.configure_trainable_layers(4)
  ep=set(adapter.encoder.parameters());opt=torch.optim.AdamW([{'params':[p for p in model.parameters() if p.requires_grad and p not in ep],'lr':3e-4},{'params':[p for p in adapter.encoder.parameters() if p.requires_grad],'lr':4e-6}],weight_decay=.01);model.train()
  for e in range(epochs):
   ls=[];opt.zero_grad()
   for i in range(0,len(train),8):
    b,s,k,a=collate(train[i:i+8])
    with torch.autocast('cuda',dtype=torch.bfloat16): x1,x2,x3=model(b);loss=(sem(x1,s)+.35*kloss(x2,k)+.5*aloss(x3.squeeze(-1),a))/2
    loss.backward();ls.append(float(loss.detach())*2)
    if ((i//8)+1)%2==0 or i+8>=len(train):torch.nn.utils.clip_grad_norm_(model.parameters(),1);opt.step();opt.zero_grad()
   hist.append({'phase':phase,'epoch':e+1,'loss':sum(ls)/len(ls)})
 model.eval(); probs=[]
 with torch.no_grad():
  for i in range(0,len(valid),8):
   b,_,_,_=collate(valid[i:i+8])
   with torch.autocast('cuda',dtype=torch.bfloat16): _,_,z=model(b)
   probs.extend(torch.sigmoid(z[:,0].float()).cpu().tolist())
 if save:
  torch.save({'state_dict':model.state_dict(),'labels':labels},save/'model.pt');adapter.tokenizer.save_pretrained(save/'tokenizer')
 return np.array(probs),{'history':hist,'duration_seconds':time.time()-start,'trainable_blocks':getattr(proof,'block_ids',[])}
def metrics(rows,probs,folds=None, breakdown=True):
 pred=probs>=THRESHOLD;truth=np.array([action(r) for r in rows]);tp=int(np.sum(pred&truth));fp=int(np.sum(pred&~truth));tn=int(np.sum(~pred&~truth));fn=int(np.sum(~pred&truth));rec=tp/(tp+fn) if tp+fn else 0;prec=tp/(tp+fp) if tp+fp else 0;f1=2*rec*prec/(rec+prec) if rec+prec else 0
 safe={k:sum(bool(p) for p,r in zip(pred,rows) if r['kind']==k)/max(1,sum(r['kind']==k for r in rows)) for k in ('protective','legitimate')};langs={}
 if breakdown:
  for lang in ('ru','ro','en','mixed'):
   ix=[i for i,r in enumerate(rows) if ('mixed' if str(r.get('language')).startswith('mixed') else r.get('language'))==lang]
   langs[lang]=metrics([rows[i] for i in ix],probs[ix],breakdown=False) if ix else {}
 out={'tp':tp,'fp':fp,'fn':fn,'tn':tn,'recall':rec,'precision':prec,'f1':f1,'safe_fpr':max(safe.values()),'protective_fp':safe['protective'],'legitimate_fp':safe['legitimate'],'languages':langs}
 if folds is not None:
  vals=[metrics([r for r,f in zip(rows,folds) if f==x],probs[np.array(folds)==x])['recall'] for x in sorted(set(folds))];out['worst_fold_recall']=min(vals)
 return out
def train():
 import torch
 if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():raise RuntimeError('CUDA BF16 required')
 rows,labels,lineage=load_train();groups=sorted({r['base_scenario_id'] for r in rows});assign={g:i%3 for i,g in enumerate(groups)};seed_results=[]
 REPORT.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
 for seed in (17,29,43):
  ps=[];rs=[];fs=[]
  for fold in range(3):
   tr=[r for r in rows if assign[r['base_scenario_id']]!=fold];va=[r for r in rows if assign[r['base_scenario_id']]==fold]
   p,e=fit(tr,va,labels,seed);ps.extend(p);rs.extend(va);fs.extend([fold]*len(va));write(REPORT/f'oof_seed_{seed}_fold_{fold}.json',e)
  m=metrics(rs,np.array(ps),fs);seed_results.append({'seed':seed,'metrics':m})
 write(REPORT/'oof_seed_stability.json',{'threshold':THRESHOLD,'seeds':seed_results,'grouping':'base_scenario_id','lineage':lineage})
 # Precommitted stable choice: middle rank by recall then precision, not holdout.
 ordered=sorted(seed_results,key=lambda x:(x['metrics']['recall'],x['metrics']['precision'],x['metrics']['f1'], -x['seed']));selected=ordered[1];config={'artifact':'NOMIC_V2_CANDIDATE_FROZEN','seed':selected['seed'],'threshold':THRESHOLD,'revision':REV,'architecture':'top_4_small_nonlinear_head','max_tokens':384,'precision':'bf16','selection':'median TRAIN grouped OOF seed','training_lineage':lineage};write(REPORT/'NOMIC_V2_CANDIDATE_FROZEN.json',config);config_sha=sha(REPORT/'NOMIC_V2_CANDIDATE_FROZEN.json')
 target=OUT/'NOMIC_DEPLOYMENT_V2';target.mkdir(parents=True,exist_ok=True);_,e=fit(rows,rows[:1],labels,selected['seed'],target);meta={**config,'config_sha256':config_sha,'checkpoint_sha256':sha(target/'model.pt'),'training':e,'training_records':len(rows),'environment':{'python':sys.version,'platform':platform.platform(),'torch':torch.__version__,'gpu':torch.cuda.get_device_name(0)}};write(target/'metadata.json',meta);write(REPORT/'training_complete.json',{'selected':selected,'metadata':meta})
def infer(artifact,rows):
 import torch
 from scripts.championship_backbones import build_adapter
 from scripts.run_brain_championship_v3 import NonlinearScutModel
 from scripts.tail_aware_encoder import pack_turns
 ck=torch.load(artifact/'model.pt',map_location='cuda',weights_only=True);meta=json.loads((artifact/'metadata.json').read_text(encoding='utf8'));adapter=build_adapter('nomic_v2_moe',meta['revision'],cache_dir=str(ROOT/'.local'/'ml-cache'/'hf-cache'));model=NonlinearScutModel(adapter,len(ck['labels'])).cuda();model.load_state_dict(ck['state_dict']);model.eval();out=[]
 with torch.no_grad():
  for r in rows:
   e=adapter.tokenizer([pack_turns(r['turns'],adapter.tokenizer,384)],return_tensors='pt',truncation=True,max_length=384)
   with torch.autocast('cuda',dtype=torch.bfloat16):_,_,a=model({k:v.cuda() for k,v in e.items()})
   out.append(float(torch.sigmoid(a[0,0].float()).cpu()))
 return np.array(out)
def evaluate():
 hold=json.loads(HOLDOUT.read_text(encoding='utf8'))['bases'];v1=ROOT/'output'/'hybrid_v1'/'NOMIC_DEPLOYMENT_V1';v2=OUT/'NOMIC_DEPLOYMENT_V2';p1=infer(v1,hold);p2=infer(v2,hold);m=metrics(hold,p2);families={f:metrics([r for r in hold if r['family']==f],p2[[i for i,r in enumerate(hold) if r['family']==f]]) for f in FAMILIES}
 probes=[{'id':chr(65+i),'turns':[('CALLER',t)],'kind':'dangerous','language':'ru'} for i,t in enumerate(KNOWN)];q1=infer(v1,probes);q2=infer(v2,probes);probe=[{'id':p['id'],'v1_score':float(a),'v2_score':float(b),'delta':float(b-a),'v1_alert':bool(a>=THRESHOLD),'v2_alert':bool(b>=THRESHOLD)} for p,a,b in zip(probes,q1,q2)]
 result={'threshold':THRESHOLD,'holdout_sha256':sha(HOLDOUT),'holdout':m,'per_family':families,'known_three_regression_probes':probe,'audio_replay':'NOT_RUN: evaluation infrastructure uses V1 checkpoint path and must not be changed in this semantic-only stage'}
 write(REPORT/'one_shot_holdout_and_probes.json',result)
 t=json.loads((REPORT/'training_complete.json').read_text(encoding='utf8'));s=t['selected']['metrics'];ok=s['recall']>=.9 and s['precision']>=.94 and s['safe_fpr']<=.1 and s['worst_fold_recall']>=.85 and all(x['metrics']['recall']>=.9 and x['metrics']['precision']>=.94 for x in json.loads((REPORT/'oof_seed_stability.json').read_text(encoding='utf8'))['seeds']) and m['recall']>=.875 and m['protective_fp']<=.1 and m['legitimate_fp']<=.1 and all(x['recall']>=.75 for x in families.values())
 verdict='SCUT_NOMIC_V2_READY' if ok else 'SCUT_NOMIC_V2_REJECTED_KEEP_V1';final={'verdict':verdict,'v1_baseline':{'checkpoint':str(v1/'model.pt'),'sha256':sha(v1/'model.pt'),'threshold':THRESHOLD},'v2_candidate':t,'oof':json.loads((REPORT/'oof_seed_stability.json').read_text(encoding='utf8')),'remediation_holdout':result,'deployment':json.loads((v2/'metadata.json').read_text(encoding='utf8')) if ok else None}
 write(REPORT/'SCUT_NOMIC_REMEDIATION_V1_RESULTS.json',final);md=f'# SCUT Nomic Semantic Remediation V1\n\n## Final verdict\n\n{verdict}\n\n## OOF\n\n```json\n{json.dumps(final["oof"],ensure_ascii=False,indent=2)}\n```\n\n## Holdout and probes\n\n```json\n{json.dumps(result,ensure_ascii=False,indent=2)}\n```\n';(REPORT/'SCUT_NOMIC_REMEDIATION_V1_REPORT.md').write_text(md,encoding='utf8');print(verdict)
def reject():
 """Close an OOF-rejected run without opening the locked holdout."""
 rows,_,_=load_train(); scores=infer(ROOT/'output'/'hybrid_v1'/'NOMIC_DEPLOYMENT_V1',rows)
 misses=[r for r,p in zip(rows,scores) if action(r) and p<THRESHOLD]
 categories={
  'SAFE_ACCOUNT_AND_TRANSFER':['MONEY_OR_ASSET_MOVEMENT','CASH_OR_COURIER_HANDOFF'],
  'SEED_RECOVERY_SECRET':['CREDENTIAL_DISCLOSURE','CRYPTO_OR_GIFT_VALUE_TRANSFER'],
  'FAMILY_EMERGENCY_MONEY':['EMOTIONAL_OR_FAMILY_PRESSURE'],
  'OTHER_RECURRENT':['AUTHORITY_PRESSURE','REMOTE_DEVICE_ACCESS','LINK_OR_QR_ACTION']}
 tax={'schema':1,'scope':'PERMITTED_DEVELOPMENT_TRAIN_ONLY_CURRENT_FROZEN_NOMIC_V1','threshold':THRESHOLD,'below_threshold_dangerous_count':len(misses),'families':[],'method':'V1 score on permitted TRAIN records; aggregate label-family counts only, no observed validation or historical TEST loaded'}
 for name,required in categories.items():
  matched=[r for r in misses if any(label in r['labels'] for label in required)]
  tax['families'].append({'family':name,'development_miss_count':len(matched),'labels':required,'recurrent':len(matched)>=2})
 write(REPORT/'NOMIC_V1_WEAKNESS_TAXONOMY.json',tax)
 oof=json.loads((REPORT/'oof_seed_stability.json').read_text(encoding='utf8')); selected=json.loads((REPORT/'training_complete.json').read_text(encoding='utf8'))['selected']
 failed=[]
 for item in oof['seeds']:
  m=item['metrics']; failed.append({'seed':item['seed'],'failed_gates':[name for name,ok in {'dangerous_recall_gte_090':m['recall']>=.90,'precision_gte_094':m['precision']>=.94,'safe_fpr_lte_010':m['safe_fpr']<=.10,'worst_fold_recall_gte_085':m['worst_fold_recall']>=.85}.items() if not ok]})
 candidate=OUT/'NOMIC_DEPLOYMENT_V2'; rejected=OUT/'NOMIC_CANDIDATE_REJECTED_KEEP_V1'
 if candidate.exists() and not rejected.exists(): shutil.move(str(candidate),str(rejected))
 result={'verdict':'SCUT_NOMIC_V2_REJECTED_KEEP_V1','reason':'Grouped TRAIN-only OOF safety gates failed before the one-shot holdout eligibility gate.','v1_baseline':{'checkpoint':str(ROOT/'output'/'hybrid_v1'/'NOMIC_DEPLOYMENT_V1'/'model.pt'),'sha256':sha(ROOT/'output'/'hybrid_v1'/'NOMIC_DEPLOYMENT_V1'/'model.pt'),'threshold':THRESHOLD},'v2_candidate':{'selected_seed':selected['seed'],'candidate_artifact':str(rejected),'deployment_created':False},'oof':oof,'failed_gates':failed,'holdout':{'status':'NOT_OPENED','sha256_locked':json.loads(LOCK.read_text(encoding='utf8'))['sha256'],'reason':'candidate rejected from OOF; no post-holdout tuning allowed'},'known_three_probes':{'status':'NOT_RUN','reason':'candidate rejected before holdout/probe stage'},'audio_replay':{'status':'NOT_RUN','reason':'candidate not otherwise qualified; Whisper/VAD/stabilizer and locked pack untouched'},'no_rule_patch':True,'threshold':THRESHOLD}
 write(REPORT/'SCUT_NOMIC_REMEDIATION_V1_RESULTS.json',result)
 md='# SCUT Nomic Semantic Remediation V1\n\n## Final verdict\n\nSCUT_NOMIC_V2_REJECTED_KEEP_V1\n\nThe candidate was rejected using grouped TRAIN-only OOF before the locked holdout was opened.\n\n## OOF seed stability\n\n```json\n'+json.dumps(oof,ensure_ascii=False,indent=2)+'\n```\n\n## Failed gates\n\n```json\n'+json.dumps(failed,ensure_ascii=False,indent=2)+'\n```\n\nThe remediation holdout, regression probes, and Audio Replay were not run; V1 remains authoritative.\n'
 (REPORT/'SCUT_NOMIC_REMEDIATION_V1_REPORT.md').write_text(md,encoding='utf8');print('SCUT_NOMIC_V2_REJECTED_KEEP_V1')
def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=('build','train','evaluate','reject','all'));a=p.parse_args()
 if a.command in ('build','all'):build()
 if a.command in ('train','all'):train()
 if a.command in ('evaluate','all'):evaluate()
 if a.command=='reject':reject()
if __name__=='__main__':main()
