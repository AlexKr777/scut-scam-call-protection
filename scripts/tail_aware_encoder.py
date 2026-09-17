"""Tokenizer-aware, deterministic transcript packing for championship models."""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any


ACTION_LABELS = frozenset({
    "CREDENTIAL_DISCLOSURE", "MONEY_OR_ASSET_MOVEMENT", "REMOTE_DEVICE_ACCESS",
    "AUTHORIZATION_OR_APPROVAL", "LINK_OR_QR_ACTION", "CASH_OR_COURIER_HANDOFF",
    "LOAN_OR_CREDIT_ACTION", "CRYPTO_OR_GIFT_VALUE_TRANSFER", "PERSONAL_DATA_DISCLOSURE",
})
EXCLUSION_LABELS = frozenset({"NEGATION", "QUOTATION", "HYPOTHETICAL"})
_OMISSION = "[CONTEXT_OMITTED]"


def _normalise_turn(turn: Sequence[str]) -> tuple[str, str]:
    if not isinstance(turn, (list, tuple)) or len(turn) != 2:
        raise ValueError("each turn must be a two-item speaker/text sequence")
    speaker, text = turn
    if not isinstance(speaker, str) or not isinstance(text, str):
        raise ValueError("turn speaker and text must be strings")
    return speaker, text


def _render(turns: Iterable[Sequence[str]]) -> str:
    return " ".join(f"[{speaker}] {text}" for speaker, text in map(_normalise_turn, turns))


def _render_packed(head: Sequence[Sequence[str]], tail: Sequence[Sequence[str]]) -> str:
    parts = []
    if head:
        parts.append(_render(head))
    parts.append(_OMISSION)
    if tail:
        parts.append(_render(tail))
    return " ".join(parts)


def _token_count(tokenizer: Any, text: str) -> int:
    encoded = tokenizer(text, add_special_tokens=True)
    return len(encoded["input_ids"])


def pack_turns(turns: Sequence[Sequence[str]], tokenizer: Any, max_tokens: int = 384, prefix: str = "") -> str:
    """Pack a transcript as head plus newest full turns without losing its final turn."""
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    normalised = [_normalise_turn(turn) for turn in turns]
    if not normalised:
        return prefix.rstrip()
    whole = prefix + _render(normalised)
    if _token_count(tokenizer, whole) <= max_tokens:
        return whole

    head = normalised[:1]
    final = normalised[-1:]
    if _token_count(tokenizer, prefix + _render_packed(head, final)) > max_tokens:
        head = []

    chosen: list[tuple[str, str]] = []
    for turn in reversed(normalised):
        candidate = prefix + _render_packed(head, [turn, *chosen])
        if _token_count(tokenizer, candidate) > max_tokens:
            break
        chosen.insert(0, turn)
    return prefix + _render_packed(head, chosen)


def dangerous_action_target(row: dict[str, Any]) -> int:
    """Return 1 only for direct, active requests for an action-bearing label."""
    labels = set(row.get("labels", ()))
    return int(
        bool(labels & ACTION_LABELS)
        and {"ACTUAL_REQUEST", "DIRECTED_AT_USER"} <= labels
        and not bool(labels & EXCLUSION_LABELS)
    )
