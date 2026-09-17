"""Always-on NLI semantic discovery for finalized caller turns."""
from __future__ import annotations
from .neural_nli import NliLabel
from .realtime_pipeline import CALLER, Utterance
from .semantic_ontology import DialogueMemory, Polarity, SemanticAction, SemanticFact, SpeechAct

CORE=(
 (SemanticAction.DISCLOSE_CREDENTIAL,"The caller wants the user to reveal an authentication secret."),
 (SemanticAction.TRANSFER_MONEY,"The caller wants the user to move money or assets to another destination."),
 (SemanticAction.REMOTE_ACCESS,"The caller wants the user to grant remote device access."),
 (SemanticAction.APPROVE_TRANSACTION,"The caller wants the user to approve or authenticate an action."),
 (SemanticAction.OPEN_EXTERNAL_RESOURCE,"The caller wants the user to open or use an external resource for a security action."),
 (SemanticAction.ISOLATION,"The caller is attempting to prevent independent verification or isolate the user."),
 (SemanticAction.URGENCY,"The caller is applying urgency or time pressure."),
 (SemanticAction.FEAR,"The caller is applying fear or authority pressure."),
)

class NeuralSemanticAnalyzer:
    def __init__(self, runtime, thresholds: dict[SemanticAction,float]|None=None): self.runtime=runtime; self.thresholds=thresholds or {}
    def _context(self, turn: Utterance, memory: DialogueMemory) -> str:
        recent=memory.turns[-7:]+[turn]
        text="\n".join(f"{item.speaker}: {item.text}" for item in recent)
        if memory.last_user_proposal: text += "\nACTIVE_USER_PROPOSITION: "+memory.last_user_proposal.value
        return text[-5000:]
    def analyze(self, turn: Utterance, memory: DialogueMemory, deterministic_facts: list[SemanticFact]) -> list[SemanticFact]:
        if turn.speaker != CALLER: return []
        context=self._context(turn,memory); pairs=[(context,hypothesis) for _,hypothesis in CORE]
        results=self.runtime.verify_pairs(pairs); facts=[]
        # Scope is not a discovery gate: the universal batch still runs, but
        # quoted/protective actions cannot become caller-directed facts.
        inert_actions={fact.action for fact in deterministic_facts if fact.polarity is not Polarity.POSITIVE}
        inert_turn=bool(inert_actions)
        for (action,_),result in zip(CORE,results):
            threshold=self.thresholds.get(action,.75)
            if not inert_turn and action not in inert_actions and result.label is NliLabel.ENTAILMENT and result.entailment >= threshold:
                facts.append(SemanticFact(action,result.entailment,CALLER,CALLER,SpeechAct.DIRECT_REQUEST,Polarity.POSITIVE,(turn.id,),"LOCAL_NLI"))
        return facts

def default_neural_analyzer() -> NeuralSemanticAnalyzer:
    from .neural_nli import default_runtime
    return NeuralSemanticAnalyzer(default_runtime())
