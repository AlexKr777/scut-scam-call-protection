"""Conservative, explainable local scam risk classifier."""
from dataclasses import dataclass
from enum import Enum
import re
from .local_semantics import LocalSemanticAnalyzer
from .realtime_pipeline import CALLER, Utterance
from .semantic_ontology import DialogueMemory, SemanticAction


class Risk(str, Enum):
    SAFE = "SAFE"
    SUSPICIOUS = "SUSPICIOUS"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Decision:
    risk: Risk
    reason: str
    source: str


NEGATION = re.compile(r"\b(do not share|never share|don't share|не сообщайте|никому не называйте|не называйте|nu comunica(?:ți|ti)|nu spune(?:ți|ti))\b", re.I)
SENSITIVE = re.compile(r"\b(otp|sms.?code|verification code|pin|cvv|password|seed phrase|recovery code|код(?:\s+из)?\s+(?:sms|смс)|смс.?код|парол[ья]|пин|cvv|cod(?:ul)?\s+(?:din\s+)?sms|parol[ăa])\b", re.I)
ACTIVE = re.compile(r"\b(tell|give|say|share|send|read|dictate|назовите|сообщите|скажите|продиктуйте|передайте|spune(?:ți|ti)|trimite(?:ți|ti)|da(?:ți|ti))\b", re.I)
PRETEXT = re.compile(r"\b(bank|security|fraud|police|support|banc[ăa]|securitate|банк|служб[аы]\s+безопасности|полици|поддержк)\b", re.I)
TRANSFER = re.compile(r"\b(transfer|send money|safe account|wire|переведите|безопасн(?:ый|ый) счет|перевод|transfer(?:ă|a)|cont sigur)\b", re.I)
REMOTE = re.compile(r"\b(anydesk|teamviewer|remote.?access|удаленн(?:ый|ого) доступ|дистанțat)\b", re.I)
SUSPICIOUS = re.compile(r"\b(urgent|immediately|blocked|arrest|suspicious transaction|срочно|немедленно|заблокирован|подозрительн|urgent|blocat)\b", re.I)


def classify_local(text: str) -> Decision:
    normalized = " ".join(text.strip().split())
    if not normalized:
        return Decision(Risk.SAFE, "No stable caller text", "LOCAL")
    facts = LocalSemanticAnalyzer().analyze(Utterance("local", CALLER, normalized, 0, 0), DialogueMemory())
    dangerous = [fact for fact in facts if fact.is_active_dangerous]
    if dangerous:
        return Decision(Risk.CRITICAL, "Caller-directed " + dangerous[0].action.value.lower(), "LOCAL_SEMANTIC")
    if any(fact.action in {SemanticAction.ISOLATION, SemanticAction.URGENCY, SemanticAction.FEAR, SemanticAction.AUTHORITY} for fact in facts):
        return Decision(Risk.SUSPICIOUS, "Psychological pressure requires context", "LOCAL_SEMANTIC")
    # Preserve the legacy multilingual fast-path while migration fixtures still
    # contain deliberately corrupted Whisper-style Cyrillic spellings.
    if NEGATION.search(normalized):
        return Decision(Risk.SAFE, "Protective/negated advice detected", "LOCAL_NEGATION")
    if ACTIVE.search(normalized) and SENSITIVE.search(normalized):
        return Decision(Risk.CRITICAL, "Active request for sensitive credential", "LOCAL_LEGACY_ASR")
    return Decision(Risk.SAFE, "No high-confidence local semantic evidence", "LOCAL")
