"""Frozen, offline, speaker-aware multilingual SCUT RULES_V1 engine.

The engine deliberately exposes evidence instead of a bare verdict.  It is
used both by the live product and the championship adapter, never as a
training-data mutation.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

VERSION = "RULES_V1"
WEIGHTS = {"actual_action": 7, "identity": 2, "urgency": 2, "pressure": 2,
           "secrecy": 2, "verification": 2, "keep_call": 2, "protective": -5}

# Every pattern is deliberately narrow: a family alone is context, whereas a
# caller-directed imperative/request is the high-confidence signal.
FAMILIES = {
 "CREDENTIALS": r"\b(otp|sms|verification|recovery|security|code|password|pin|cvv|cvc|код|кода|кодик|парол[ья]|пин|цифр[ыауе]|cod(?:ul)?|parol[ăa]|cifrele)\b",
 "MONEY_MOVEMENT": r"\b(transfer|send money|move (?:the )?funds|safe account|reserve account|wire|payment|перевед|безопасн(?:ый|ый счет)|средств|отправьте деньги|transfer[ăa]|trimite(?:ți)? bani|cont sigur|mutați fondurile)\b",
 "REMOTE_ACCESS": r"\b(anydesk|teamviewer|rustdesk|remote (?:access|desktop|support)|screen shar|support control|удаленн(?:ый|ого) доступ|демонстрац(?:ию|ия) экрана|удален[ыо]й доступ|acces la distanță|control la distanță)\b",
 "LINK_DOWNLOAD": r"\b(link|url|website|scan qr|qr code|download|apk|attachment|ссылк[ауе]|скачайт[еь]|откройте сайт|qr|linkul|descarc[ăa]|scanați)\b",
 "PERSONAL_DATA": r"\b(passport|identity card|document photo|personal number|card number|expiry|account details|паспорт|документ|номер карт|срок действия|buletin|pașaport|date personale|număr card)\b",
 "CASH_COURIER": r"\b(withdraw cash|courier|hand (?:over|cash)|cash collection|снимите наличные|курьер|передайте наличные|retrageți numerar|curier)\b",
 "CRYPTO_GIFTCARD": r"\b(usdt|crypto|bitcoin|wallet|seed phrase|private key|gift ?card|крипт|сид фраз|подарочн.*карт|cripto|portofel|card cadou)\b",
 "LOAN": r"\b(loan|credit|cancel.*loan|кредит|займ|отмен.*кредит|împrumut|credit)\b",
 "PARCEL_MARKETPLACE": r"\b(parcel|customs|delivery fee|refund|buyer|seller|receive-money|посылк|тамож|доставк|возврат|покупател|colet|vamă|livrare|rambursare|cumpărător)\b",
 "FAMILY_EMERGENCY": r"\b(relative.*danger|emergency|hospital|accident|родственник.*бед|срочно.*больниц|ruda.*pericol|urgență|spital)\b",
}
IDENTITY = r"\b(bank|police|prosecutor|tax|telecom|government|post|courier|microsoft|apple|security department|банк|полици|прокуратур|налог|оператор|госуслуг|служб[аы] безопасности|banc[ăa]|poliți[ae]|procuror|operator|guvern)\b"
DIRECTIVE = r"\b(read|tell|say|give|send|move|transfer|install|download|open|scan|share|allow|confirm|назовите|скажите|сообщите|дайте|переведите|отправьте|установите|скачайте|откройте|разрешите|прочитайте|spuneți|trimiteți|mutați|transferați|instalați|deschideți|permiteți|citiți)\b"
URGENCY = r"\b(urgent|immediately|now|today|blocked|loss|arrest|срочно|немедленно|сейчас|заблокир|потеряете|арест|urgent|imediat|acum|blocat|pierdeți)\b"
SECRECY = r"\b(don't tell|do not tell|stay on (?:the )?line|don't hang up|не говорите|никому не|не кладите трубку|оставайтесь на линии|nu spuneți|nimănui|nu închideți)\b"
PROTECTIVE = r"\b(never (?:read|share|give|send)|do not (?:read|share|give|send)|don't (?:read|share|give|send)|никому не (?:сообщайте|говорите|называйте|давайте)|не сообщайте|не называйте|nu (?:comunicați|spuneți|trimiteți)|niciodată nu)\b"
HYPOTHETICAL = r"\b(if i (?:asked|were to ask)|for example|например|если бы|если я попрошу|dacă aș|de exemplu)\b"
QUOTE = r"(?:[\"'«]|\b(?:he|she|он|она|a spus|said)\b)"

def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("ё", "е").replace("ă", "a").replace("â", "a").replace("î", "i").replace("ș", "s").replace("ţ", "t").replace("ț", "t")
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s'-]", " ", text)).strip()

def languages(text: str) -> list[str]:
    result=[]; raw=text.casefold()
    if re.search(r"[а-яё]", raw): result.append("ru")
    if re.search(r"\b(nu|spuneti|codul|banca|transferati|nimanui|acum)\b|[ăâîșț]", raw): result.append("ro")
    if re.search(r"\b(the|you|your|code|bank|transfer|remote|read|don't|anydesk|teamviewer|rustdesk)\b", raw): result.append("en")
    return result or ["unknown"]

def _match(pattern: str, text: str) -> bool: return bool(re.search(pattern, text, re.I))

@dataclass
class RulesV1:
    def analyze(self, turns: Iterable[tuple[str, str] | dict[str, Any]]) -> dict[str, Any]:
        items=[]; active_identity=False; pressure=False; reasons=[]; langs=[]; actions=[]; evidence=[]
        for index, turn in enumerate(turns):
            speaker, raw = (turn.get("speaker", "CALLER"), turn.get("text", "")) if isinstance(turn, dict) else turn
            speaker=str(speaker).upper(); text=normalize(str(raw)); turn_langs=languages(str(raw)); langs.extend(turn_langs)
            protective=_match(PROTECTIVE,text); hypothetical=_match(HYPOTHETICAL,text); quote=_match(QUOTE,str(raw))
            negation=protective or bool(re.search(r"\b(not|never|don't|не|ни|nu)\b", text))
            identity=_match(IDENTITY,text); urgent=_match(URGENCY,text); secrecy=_match(SECRECY,text)
            families=[name for name, pattern in FAMILIES.items() if _match(pattern,text)]
            directive=_match(DIRECTIVE,text)
            actual = speaker in {"CALLER","REMOTE","REMOTE_SPEAKER"} and bool(families) and directive and not (protective or hypothetical or quote)
            if identity and speaker in {"CALLER","REMOTE","REMOTE_SPEAKER"}: active_identity=True
            if urgent or secrecy: pressure=True
            if actual:
                actions.extend(families)
                for family in families:
                    evidence.append({"code":"ACTUAL_"+family,"turn_id":index,"speaker":speaker,"family":family,"strength":"high","text":str(raw)[:180]})
            elif identity or urgent or secrecy:
                evidence.append({"code":"CONTEXT_IDENTITY" if identity else "PRESSURE","turn_id":index,"speaker":speaker,"strength":"low","text":str(raw)[:180]})
            items.append({"turn_id":index,"speaker":speaker,"languages":turn_langs,"protective_advice":protective,"negation":negation,"quotation":quote,"hypothetical":hypothetical})
        action_score=min(1.0, .85 if actions else 0.0)
        risk=max(0, sum(WEIGHTS["actual_action"] for _ in set(actions)) + (WEIGHTS["identity"] if active_identity else 0) + (WEIGHTS["urgency"] if pressure else 0) + (WEIGHTS["protective"] if not actions and any(x["protective_advice"] for x in items) else 0))
        scam_family=sorted(set(actions))
        reasons=["CALLER_DIRECTED_"+x for x in scam_family]
        if active_identity: reasons.append("CLAIMED_AUTHORITY_OR_SERVICE")
        if pressure: reasons.append("PRESSURE_OR_ISOLATION")
        return {"scam_family":scam_family,"requested_actions":scam_family,"caller_claimed_identity":active_identity,"actual_request":bool(actions),"directed_at_user":bool(actions),"credentials_request":"CREDENTIALS" in actions,"money_request":"MONEY_MOVEMENT" in actions,"remote_access_request":"REMOTE_ACCESS" in actions,"link_or_qr_request":"LINK_DOWNLOAD" in actions,"personal_data_request":"PERSONAL_DATA" in actions,"authority_pressure":active_identity and pressure,"urgency":pressure,"fear_or_threat":pressure,"secrecy":pressure,"keep_call_active":pressure,"discourage_verification":pressure,"protective_advice":any(x["protective_advice"] for x in items),"negation":any(x["negation"] for x in items),"quotation":any(x["quotation"] for x in items),"hypothetical":any(x["hypothetical"] for x in items),"languages_seen":sorted(set(langs)),"language_per_turn":items,"risk_score":risk,"action_score":action_score,"evidence_strength":"high" if actions else "low" if evidence else "none","evidence_turn_ids":[x["turn_id"] for x in evidence],"evidence_items":evidence,"reason_codes":reasons,"human_readable_reasons":reasons}

def analyze(turns: Iterable[tuple[str,str] | dict[str,Any]]) -> dict[str,Any]: return RulesV1().analyze(turns)
