"""Local fixed-output pragmatic extraction for finalized utterances."""
from __future__ import annotations
from .realtime_pipeline import CALLER, Utterance
from .semantic_ontology import DialogueMemory, Polarity, SemanticAction, SemanticFact, SpeechAct
def _has(text: str, *terms: str) -> bool: return any(term in text for term in terms)
class LocalSemanticAnalyzer:
    _directive=("tell","give","read","say","enter","move","transfer","send","install","open","scan","approve","withdraw","take","dictate","дикту","скаж","назов","сообщ","прочита","перевед","отправ","установ","открой","подтверд","введ","muta","transfer","spune","comunica","instala","deschide")
    _protective=("never share","do not share","don't share","do not tell","never give","никому не","не сообщайте","не называйте","nu comunica","nu spune","nu oferi")
    _quote=("scammers say","fraudsters say","scammers ask","fraudsters ask","training says","security training","example:","for example","мошенники говорят","мошенники просят","escrocii spun","escrocii cer")
    _confirmation=("yes","exactly","correct","да","именно","совершенно верно","da,")
    def analyze(self, turn: Utterance, memory: DialogueMemory) -> list[SemanticFact]:
        text=" ".join(turn.text.lower().split()); caller=turn.speaker==CALLER
        if not text: return []
        quoted=_has(text,*self._quote) and not _has(text,"now ","now,","а теперь","acum ")
        # "nu spuneți" beside a transfer is secrecy, not advice not to disclose a credential.
        credential_context=_has(text,"sms","otp","pin","cvv","password","code","confirmation number","six digits","код","смс","parol","codul")
        protective=_has(text,*self._protective) and credential_context; facts=[]
        def add(action, confidence, dangerous=True, speech=SpeechAct.DIRECT_REQUEST):
            polarity=Polarity.QUOTED if quoted else (Polarity.NEGATED if protective else Polarity.POSITIVE)
            facts.append(SemanticFact(action,confidence,turn.speaker,CALLER if caller and dangerous else turn.speaker,SpeechAct.QUOTATION if quoted else (SpeechAct.PROTECTIVE_ADVICE if protective else speech),polarity,(turn.id,)))
        if caller and memory.last_user_proposal and _has(text,*self._confirmation): add(memory.last_user_proposal,.94,True,SpeechAct.CONFIRMATION)
        directed=_has(text,*self._directive)
        credential=_has(text,"sms","otp","pin","cvv","password","code","confirmation number","six digits","digits that arrived","код","смс","цифр","parol","codul","cod ")
        money=_has(text,"transfer","move funds","move the money","move money","safe account","details i","bank details","money to","place the balance","temporarily place","banii","mută","mutați","перевед","средств","реквизит")
        remote=_has(text,"remote","support application","support app","connection id","session id","screen share","device control","удален","приложение поддержки","id подключения") and _has(text,"install","open","tell","give","установ","скаж","назов")
        external=_has(text,"page i sent","link i sent","open the link","qr","странице","ссылк")
        if credential and (directed or _has(text,"six digits","confirmation number")): add(SemanticAction.DISCLOSE_CREDENTIAL,.96)
        if money and (directed or _has(text,"now","acum","сейчас")): add(SemanticAction.TRANSFER_MONEY,.95)
        if remote: add(SemanticAction.REMOTE_ACCESS,.94)
        if external and directed: add(SemanticAction.OPEN_EXTERNAL_RESOURCE,.89)
        if _has(text,"approve","confirm the transaction","подтверд") and directed: add(SemanticAction.APPROVE_TRANSACTION,.88)
        if _has(text,"take a loan","open credit","взять кредит") and directed: add(SemanticAction.TAKE_LOAN,.90)
        if _has(text,"withdraw cash","cash courier","снять наличные","курьер") and directed: add(SemanticAction.WITHDRAW_CASH if _has(text,"withdraw","снять") else SemanticAction.HAND_CASH_TO_COURIER,.90)
        if caller and _has(text,"don't tell","do not tell","don't call","do not call","никому","не звоните","nu spune") and not protective: add(SemanticAction.ISOLATION,.84,False,SpeechAct.ASSERTION)
        if caller and _has(text,"now","urgent","immediately","срочно","сейчас","acum"): add(SemanticAction.URGENCY,.72,False,SpeechAct.ASSERTION)
        if caller and _has(text,"arrest","police","illegal package","blocked","уголов","полици","заблок"): add(SemanticAction.FEAR,.70,False,SpeechAct.ASSERTION)
        return facts
