"""SCUT Hybrid Brain V1: deterministic evidence extraction and evidence-gated fusion.

This module deliberately does not read any corpus, TEST, validation, or benchmark file.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
import time
from typing import Any, Iterable

from .realtime_pipeline import CALLER, USER, Utterance


class RiskLevel(str, Enum):
    SAFE = "SAFE"; WATCH = "WATCH"; SUSPICIOUS = "SUSPICIOUS"; HIGH_RISK = "HIGH_RISK"; CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Evidence:
    code: str; confidence: float; speaker: str; turn_ids: tuple[str, ...]
    normalized_span: str = ""; original_span: str = ""; languages: tuple[str, ...] = ()
    detector: str = "EVIDENCE_RULES_V2"; family: str | None = None; explanation_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self); result["turn_ids"] = list(self.turn_ids); result["languages"] = list(self.languages); return result


@dataclass
class NomicSignal:
    action_score: float = 0.0
    semantic_scores: dict[str, float] = field(default_factory=dict)
    kind_scores: dict[str, float] = field(default_factory=dict)
    source: str = "UNAVAILABLE"


@dataclass
class ConversationState:
    """Bounded, expiry-aware conversation facts. Strong actions live longer than pressure."""
    evidence: list[Evidence] = field(default_factory=list)
    languages_seen: set[str] = field(default_factory=set)
    claimed_identities: set[str] = field(default_factory=set)
    requested_actions: set[str] = field(default_factory=set)
    current_risk: RiskLevel = RiskLevel.SAFE
    emitted_alert: RiskLevel = RiskLevel.SAFE
    turn_number: int = 0

    def ingest(self, items: Iterable[Evidence]) -> None:
        self.turn_number += 1
        self.evidence.extend(items)
        for item in items:
            self.languages_seen.update(item.languages)
            if item.code.startswith("CLAIM_"): self.claimed_identities.add(item.code)
            if item.code.startswith("REQUEST_") and item.code not in {"REQUEST_OPEN_LINK", "REQUEST_SCAN_QR"}: self.requested_actions.add(item.code)
        # Pressure expires after eight turns; explicit caller actions after thirty-two.
        weak = {"URGENCY", "FEAR", "THREAT", "SECRECY", "KEEP_CALL_ACTIVE", "DISCOURAGE_VERIFICATION", "DISCOURAGE_CONTACT_WITH_BANK", "DISCOURAGE_CONTACT_WITH_POLICE", "DISCOURAGE_CONTACT_WITH_RELATIVE"}
        self.evidence = [item for item in self.evidence if self.turn_number - _turn(item) <= (8 if item.code in weak else 32)][-128:]

    def active(self, codes: set[str] | None = None) -> list[Evidence]:
        return [item for item in self.evidence if codes is None or item.code in codes]


def _turn(item: Evidence) -> int:
    for value in item.turn_ids:
        if value.startswith("turn-") and value[5:].isdigit(): return int(value[5:])
    return 0


def detect_languages(text: str) -> tuple[str, ...]:
    found: list[str] = []
    if re.search(r"[а-яёіїє]", text.lower()): found.append("ru")
    # Romanian diacritics are decisive; common words catch ASR/no-diacritic forms.
    if re.search(r"[ăâîșşțţ]", text.lower()) or re.search(r"\b(nu|codul|banii|spune|transfera|contul)\b", text.lower()): found.append("ro")
    if re.search(r"\b(the|your|code|please|transfer|account|call|from)\b", text.lower()): found.append("en")
    return tuple(found or ["unknown"])


def normalize(text: str) -> str:
    return " ".join(text.casefold().replace("ё", "е").replace("ș", "s").replace("ş", "s").replace("ț", "t").replace("ţ", "t").split())


class EvidenceRulesV2:
    """Action/relation rules; bare scam-topic words never constitute an action."""
    VERSION = "EVIDENCE_RULES_V2"
    _direct = re.compile(r"\b(tell|give|read|say|enter|send|move|transfer|install|open|scan|allow|share|provide|dictate|spune(?:ti)?|da(?:ti)?|citeste|trimite(?:ti)?|muta(?:ti)?|transfera(?:ti)?|instaleaza|deschide(?:ti)?|permite(?:ti)?|назовите|назови|сообщите|скажите|прочитайте|введите|переведите|отправьте|установите|откройте|разрешите|передайте)\b", re.I)
    _protective = re.compile(r"\b(never|do not|don't|nu|никому не|не сообщайте|не называйте).{0,48}\b(code|cod|sms|otp|pin|password|парол|код)\b", re.I)
    _discussion = re.compile(r"\b(scammer|fraudster|scam|education|training|example|escroc|frauda|мошенн|например|обучен)\b", re.I)
    _quote = re.compile(r"\b(he said|she said|they said|asks? for|spune ca|говорит|сказал|спрашивает)\b", re.I)
    _disclaimer = re.compile(r"\b(not asking|never ask|do not ask|don't need|nu cer|nu va cerem|не прошу|не запрашиваем|не нужен)\b", re.I)

    _actions = (
        ("REQUEST_OTP", "CREDENTIAL", r"\b(sms|otp|verification|confirm(?:ation)?|six digits?|code|cod(?:ul)?|код|смс|цифр)\b"),
        ("REQUEST_PASSWORD", "CREDENTIAL", r"\b(password|parola|парол)\b"),
        ("REQUEST_PIN", "CREDENTIAL", r"\b(pin)\b"), ("REQUEST_CVV", "CREDENTIAL", r"\b(cvv|cvc)\b"),
        ("REQUEST_MONEY_TRANSFER", "MONEY", r"\b(transfer|move (?:the )?(?:money|funds)|send money|banii|muta(?:ti)?|transfera(?:ti)?|переведите|средства|деньги)\b"),
        ("REQUEST_SAFE_ACCOUNT_TRANSFER", "MONEY", r"\b(safe|secure|reserve|protected|безопасн\w*|резервн\w*)\s+(?:account|cont\w*|счет)\b|\b(?:cont\w*|счет)\s+(?:sigur|securizat|безопасн\w*|резервн\w*)\b"),
        ("REQUEST_CRYPTO_TRANSFER", "CRYPTO", r"\b(crypto|bitcoin|usdt|wallet|крипт\w*|кошелек)\b"),
        ("REQUEST_GIFT_CARD", "VALUE", r"\b(gift card|voucher|подарочн\w* карт)\b"),
        ("REQUEST_REMOTE_ACCESS", "REMOTE", r"\b(anydesk|teamviewer|remote access|screen control|удаленн\w* доступ)\b"),
        ("REQUEST_APP_INSTALL", "REMOTE", r"\b(install|instaleaza|установите).{0,35}\b(app|application|anydesk|teamviewer|приложен)\b"),
        ("REQUEST_OPEN_LINK", "LINK", r"\b(open|click|deschide(?:ti)?|откройте).{0,24}\b(link|ссылк\w*)\b"),
        ("REQUEST_SCAN_QR", "LINK", r"\b(scan|scaneaza|сканируйте).{0,24}\b(qr)\b"),
        ("REQUEST_CASH_TO_COURIER", "CASH", r"\b(courier|curier|курьер).{0,40}\b(cash|money|bani|наличн)\b|\b(cash|bani|наличн).{0,40}\b(courier|curier|курьер)\b"),
        ("REQUEST_SEED_PHRASE", "CREDENTIAL", r"\b(seed phrase|recovery phrase|сид фраз|секретн\w* фраз)\b"),
        ("REQUEST_PRIVATE_KEY", "CREDENTIAL", r"\b(private key|cheie privata|приватн\w* ключ)\b"),
    )

    def analyze(self, turn: Utterance, state: ConversationState) -> list[Evidence]:
        text, original = normalize(turn.text), turn.text
        turn_id = f"turn-{state.turn_number + 1}"; langs = detect_languages(text); found: list[Evidence] = []
        def add(code: str, confidence: float, family: str | None = None) -> None:
            found.append(Evidence(code, confidence, turn.speaker, (turn_id,), text, original[:240], langs, family=family, explanation_code=_reason(code)))
        if turn.speaker == USER:
            if self._direct.search(text) or re.search(r"\b(asking|cere|просит)\b", text): add("USER_REPETITION", .95)
            return found
        protective = bool(self._protective.search(text))
        contextual = bool(self._discussion.search(text) or self._quote.search(text))
        if protective:
            add("PROTECTIVE_ADVICE", .99); add("NEGATION", .98)
            if re.search(r"\b(if|daca|если|someone|cineva|кто)\b", text): add("HYPOTHETICAL", .92)
        if contextual: add("SCAM_DISCUSSION" if self._discussion.search(text) else "QUOTATION", .90)
        for code, family, pattern in self._actions:
            if not re.search(pattern, text, re.I): continue
            action_directed = bool(self._direct.search(text)) or (code == "REQUEST_OTP" and bool(re.search(r"\b(six|6|шесть|sase)\b.{0,20}\b(digit|digits|цифр|cifre)\b", text)))
            if action_directed and not (protective or contextual):
                add(code, .98 if code in {"REQUEST_OTP", "REQUEST_SAFE_ACCOUNT_TRANSFER", "REQUEST_REMOTE_ACCESS"} else .94, family); add("ACTUAL_REQUEST", .98, family); add("DIRECTED_AT_USER", .96, family)
        # Identity and supporting signals are asserted facts, never enough for a severe alert alone.
        for code, pattern in (("CLAIM_BANK", r"\b(bank|banca|банк)\b"), ("CLAIM_POLICE", r"\b(police|politia|полици)\b"), ("CLAIM_TECH_SUPPORT", r"\b(support|suport|поддержк)\b"), ("CLAIM_DELIVERY", r"\b(delivery|livrare|доставк)\b"), ("URGENCY", r"\b(now|urgent|immediately|acum|urgent|срочно|сейчас)\b"), ("SECRECY", r"\b(don't tell|keep secret|nu spune|никому не говорите)\b"), ("KEEP_CALL_ACTIVE", r"\b(stay on (?:the )?line|don't hang up|ramaneti pe fir|не кладите трубку)\b"), ("DISCOURAGE_VERIFICATION", r"\b(don't call (?:your )?bank|do not verify|nu sunati banca|не звоните в банк)\b")):
            if re.search(pattern, text, re.I) and not protective: add(code, .84 if code.startswith("CLAIM_") else .80)
        if self._disclaimer.search(text) and any(x.code == "ACTUAL_REQUEST" for x in found): add("DISCLAIMER_CONTRADICTION", .99)
        return found


def _reason(code: str) -> str:
    return {"REQUEST_OTP": "OTP_REQUESTED", "REQUEST_MONEY_TRANSFER": "MONEY_TRANSFER_REQUESTED", "REQUEST_SAFE_ACCOUNT_TRANSFER": "MONEY_TRANSFER_REQUESTED", "REQUEST_REMOTE_ACCESS": "REMOTE_ACCESS_REQUESTED", "PROTECTIVE_ADVICE": "PROTECTIVE_ADVICE_DETECTED", "CLAIM_BANK": "IDENTITY_BANK_CLAIMED", "URGENCY": "URGENCY_DETECTED", "SECRECY": "SECRECY_REQUESTED", "DISCOURAGE_VERIFICATION": "VERIFYING_DISCOURAGED", "KEEP_CALL_ACTIVE": "KEEP_CALL_ACTIVE_DETECTED"}.get(code, code)


class HybridRiskEngineV1:
    """Nomic-led, evidence-gated monotonic policy. Rules are not an equal vote."""
    critical = {"REQUEST_OTP", "REQUEST_SAFE_ACCOUNT_TRANSFER", "REQUEST_REMOTE_ACCESS", "REQUEST_SEED_PHRASE", "REQUEST_PRIVATE_KEY"}
    strong = critical | {"REQUEST_PASSWORD", "REQUEST_PIN", "REQUEST_CVV", "REQUEST_MONEY_TRANSFER", "REQUEST_CRYPTO_TRANSFER", "REQUEST_GIFT_CARD", "REQUEST_CASH_TO_COURIER", "REQUEST_OPEN_LINK", "REQUEST_SCAN_QR", "REQUEST_APP_INSTALL"}

    def decide(self, state: ConversationState, nomic: NomicSignal) -> dict[str, Any]:
        items = state.active(); codes = {x.code for x in items}; actions = sorted(codes & self.strong)
        protective_only = "PROTECTIVE_ADVICE" in codes and not actions
        pressure = len(codes & {"URGENCY", "SECRECY", "KEEP_CALL_ACTIVE", "DISCOURAGE_VERIFICATION", "CLAIM_BANK", "CLAIM_POLICE", "CLAIM_TECH_SUPPORT"})
        score, level, trace = min(100, round(nomic.action_score * 55)), RiskLevel.SAFE, [f"nomic.action_score={nomic.action_score:.3f}"]
        if protective_only:
            level, score = (RiskLevel.WATCH if nomic.action_score >= .85 else RiskLevel.SAFE), min(score, 25); trace.append("protective_context_suppresses_unexplained_nomic_escalation")
        elif codes & self.critical:
            score = max(score, 78 if nomic.action_score < .45 else 90); level = RiskLevel.CRITICAL if nomic.action_score >= .75 else RiskLevel.HIGH_RISK; trace.append("critical_explicit_action_gate")
        elif codes & self.strong:
            score = max(score, 70 if nomic.action_score < .45 else 82); level = RiskLevel.HIGH_RISK; trace.append("strong_action_gate")
        elif nomic.action_score >= .85:
            level, score = RiskLevel.SUSPICIOUS, max(score, 60); trace.append("nomic_high_without_explainable_action")
        elif nomic.action_score >= .55 and pressure >= 3:
            level, score = RiskLevel.HIGH_RISK, max(score, 72); trace.append("moderate_nomic_plus_accumulated_pressure")
        elif nomic.action_score >= .45 or pressure >= 2:
            level, score = RiskLevel.WATCH if pressure < 3 else RiskLevel.SUSPICIOUS, max(score, 35 + pressure * 5); trace.append("collect_more_context")
        state.current_risk = level
        reasons = sorted({_reason(x.code) for x in items if x.code in codes})
        action_reasons = [_reason(x.code) for x in items if x.code in self.strong]
        primary = action_reasons[0] if action_reasons else (reasons[0] if reasons else "NOMIC_SEMANTIC_SIGNAL")
        return {"risk_level": level.value, "risk_score": score, "alert_recommended": level in {RiskLevel.HIGH_RISK, RiskLevel.CRITICAL}, "primary_reason_code": primary, "scam_families": sorted({x.family for x in items if x.family}), "requested_actions": actions, "nomic": {"action_score": nomic.action_score, "semantic_scores": nomic.semantic_scores, "kind_scores": nomic.kind_scores, "source": nomic.source}, "evidence": [x.to_dict() for x in items], "protective_context": [x.to_dict() for x in items if x.code in {"PROTECTIVE_ADVICE", "NEGATION", "HYPOTHETICAL", "QUOTATION", "SCAM_DISCUSSION"}], "conversation_state": {"languages_seen": sorted(state.languages_seen), "claimed_identity": sorted(state.claimed_identities), "active_pressure_signals": sorted(codes & {"URGENCY", "SECRECY", "KEEP_CALL_ACTIVE", "DISCOURAGE_VERIFICATION"})}, "explanation": {"reason_codes": reasons, "evidence_turn_ids": sorted({turn for x in items for turn in x.turn_ids})}, "decision_trace": trace}


class HybridBrainV1:
    def __init__(self) -> None: self.rules, self.state, self.risk = EvidenceRulesV2(), ConversationState(), HybridRiskEngineV1()
    def ingest(self, turn: Utterance, nomic: NomicSignal | None = None) -> dict[str, Any]:
        self.state.ingest(self.rules.analyze(turn, self.state)); return self.risk.decide(self.state, nomic or NomicSignal())
