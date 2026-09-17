"""Typed local semantic evidence; transcript text never controls SCUT behavior."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from .realtime_pipeline import CALLER, Utterance

class SemanticAction(str, Enum):
    DISCLOSE_CREDENTIAL="DISCLOSE_CREDENTIAL"; TRANSFER_MONEY="TRANSFER_MONEY"; REMOTE_ACCESS="REMOTE_ACCESS"; OPEN_EXTERNAL_RESOURCE="OPEN_EXTERNAL_RESOURCE"; APPROVE_TRANSACTION="APPROVE_TRANSACTION"; TAKE_LOAN="TAKE_LOAN"; WITHDRAW_CASH="WITHDRAW_CASH"; HAND_CASH_TO_COURIER="HAND_CASH_TO_COURIER"; ISOLATION="ISOLATION"; URGENCY="URGENCY"; FEAR="FEAR"; AUTHORITY="AUTHORITY"
class SpeechAct(str, Enum): DIRECT_REQUEST="DIRECT_REQUEST"; INDIRECT_REQUEST="INDIRECT_REQUEST"; CONFIRMATION="CONFIRMATION"; PROTECTIVE_ADVICE="PROTECTIVE_ADVICE"; QUOTATION="QUOTATION"; HYPOTHETICAL="HYPOTHETICAL"; ASSERTION="ASSERTION"
class Polarity(str, Enum): POSITIVE="POSITIVE"; NEGATED="NEGATED"; QUOTED="QUOTED"
class FactLifecycle(str, Enum): OBSERVED="OBSERVED"; CONFIRMED="CONFIRMED"; HISTORICAL="HISTORICAL"

@dataclass(frozen=True)
class SemanticFact:
    action: SemanticAction; confidence: float; actor: str; requester: str; speech_act: SpeechAct; polarity: Polarity; utterance_ids: tuple[str,...]; source: str="LOCAL_SEMANTIC"; lifecycle: FactLifecycle=FactLifecycle.OBSERVED; resolved_reference: str|None=None
    @property
    def is_active_dangerous(self) -> bool:
        return self.polarity is Polarity.POSITIVE and self.requester == CALLER and self.action in {SemanticAction.DISCLOSE_CREDENTIAL,SemanticAction.TRANSFER_MONEY,SemanticAction.REMOTE_ACCESS,SemanticAction.OPEN_EXTERNAL_RESOURCE,SemanticAction.APPROVE_TRANSACTION,SemanticAction.TAKE_LOAN,SemanticAction.WITHDRAW_CASH,SemanticAction.HAND_CASH_TO_COURIER}

@dataclass
class DialogueMemory:
    turns: list[Utterance]=field(default_factory=list); facts: list[SemanticFact]=field(default_factory=list); last_user_proposal: SemanticAction|None=None
    def ingest(self, turn: Utterance, facts: list[SemanticFact]) -> None:
        self.turns.append(turn); self.turns[:]=self.turns[-32:]; self.facts.extend(facts); self.facts[:]=self.facts[-64:]
        if turn.speaker != CALLER:
            for fact in facts:
                if fact.action in {SemanticAction.TRANSFER_MONEY,SemanticAction.DISCLOSE_CREDENTIAL,SemanticAction.REMOTE_ACCESS}: self.last_user_proposal=fact.action
