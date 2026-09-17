"""Explicit backbone adapters for the isolated SCUT championship."""
from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Mapping

import torch
from torch import Tensor, nn


CANDIDATES: dict[str, dict[str, Any]] = {
    "e5_base": {"model_id": "intfloat/multilingual-e5-base", "pooling": "mean", "trust_remote_code": False},
    "xlmr_base": {"model_id": "FacebookAI/xlm-roberta-base", "pooling": "first_token", "trust_remote_code": False},
    "gte_mlm_base": {"model_id": "Alibaba-NLP/gte-multilingual-mlm-base", "pooling": "mean", "trust_remote_code": True},
    "nomic_v2_moe": {"model_id": "nomic-ai/nomic-embed-text-v2-moe", "pooling": "mean", "trust_remote_code": True},
}


class TechnicalExclusion(RuntimeError):
    """A concrete architecture/preflight incompatibility; never a substitute cue."""


@dataclass(frozen=True)
class TrainableProof:
    block_ids: list[str]
    encoder_trainable_parameters: int
    encoder_total_parameters: int


class BackboneAdapter:
    """Owns supported block discovery and architecture-specific pooling."""

    def __init__(self, candidate_id: str, revision: str, tokenizer: Any, encoder: nn.Module, *, pooling: str):
        if candidate_id not in CANDIDATES and candidate_id != "fake":
            raise ValueError(f"unknown championship candidate: {candidate_id}")
        if pooling not in {"mean", "first_token"}:
            raise TechnicalExclusion(f"unsupported documented pooling representation: {pooling}")
        self.candidate_id = candidate_id
        self.model_id = CANDIDATES.get(candidate_id, {}).get("model_id", candidate_id)
        self.revision = revision
        self.tokenizer = tokenizer
        self.encoder = encoder
        self.pooling = pooling
        hidden_size = getattr(getattr(encoder, "config", None), "hidden_size", None)
        if not isinstance(hidden_size, int) or hidden_size <= 0:
            raise TechnicalExclusion(f"{candidate_id} has no positive config.hidden_size")
        self.hidden_size = hidden_size

    def _blocks(self) -> list[nn.Module]:
        # Nomic v2 MoE remote code: NomicBertModel.encoder is a
        # NomicBertEncoder and its `layers` ModuleList is the logical
        # transformer sequence; MoE experts are children of selected blocks.
        if self.candidate_id == "nomic_v2_moe":
            try:
                blocks = self.encoder.encoder.layers
            except AttributeError as exc:
                raise TechnicalExclusion("nomic_v2_moe missing encoder.encoder.layers") from exc
            if not isinstance(blocks, nn.ModuleList) or not all(isinstance(x, nn.Module) for x in blocks):
                raise TechnicalExclusion("nomic_v2_moe encoder.encoder.layers is not a logical block ModuleList")
            return list(blocks)
        # The standard BERT/RoBERTa layout covers E5, XLM-R and supported mGTE
        # releases.  Remote-code models must expose one of these documented
        # transformer-stack layouts rather than being coerced into another one.
        candidates = (
            ("model.layers", lambda: self.encoder.model.layers),
            ("model.transformer.layers", lambda: self.encoder.model.transformer.layers),
            ("transformer.blocks", lambda: self.encoder.transformer.blocks),
            ("encoder.layer", lambda: self.encoder.encoder.layer),
            ("model.encoder.layer", lambda: self.encoder.model.encoder.layer),
            ("transformer.h", lambda: self.encoder.transformer.h),
        )
        for _name, getter in candidates:
            try:
                blocks = getter()
            except (AttributeError, TypeError):
                continue
            if isinstance(blocks, (nn.ModuleList, list, tuple)) and all(isinstance(block, nn.Module) for block in blocks):
                return list(blocks)
        raise TechnicalExclusion(f"{self.candidate_id} exposes no supported transformer block sequence")

    @property
    def block_ids(self) -> list[str]:
        return [str(index) for index, _ in enumerate(self._blocks())]

    @property
    def architecture_path(self) -> str:
        if self.candidate_id == "nomic_v2_moe": return "encoder.encoder.layers"
        for name, getter in (("model.layers", lambda: self.encoder.model.layers), ("model.transformer.layers", lambda: self.encoder.model.transformer.layers), ("transformer.blocks", lambda: self.encoder.transformer.blocks), ("encoder.layer", lambda: self.encoder.encoder.layer), ("model.encoder.layer", lambda: self.encoder.model.encoder.layer), ("transformer.h", lambda: self.encoder.transformer.h)):
            try:
                if getter() is not None: return name
            except (AttributeError, TypeError): pass
        raise TechnicalExclusion(f"{self.candidate_id} has no supported architecture path")

    def configure_trainable_layers(self, depth: int) -> TrainableProof:
        if depth not in {2, 4}:
            raise ValueError("championship depth must be top_2 or top_4")
        blocks = self._blocks()
        if len(blocks) < depth:
            raise TechnicalExclusion(f"{self.candidate_id} has {len(blocks)} blocks, cannot unfreeze top_{depth}")
        for parameter in self.encoder.parameters():
            parameter.requires_grad_(False)
        selected = blocks[-depth:]
        for block in selected:
            for parameter in block.parameters():
                parameter.requires_grad_(True)
        return TrainableProof(
            block_ids=[str(index) for index in range(len(blocks) - depth, len(blocks))],
            encoder_trainable_parameters=sum(parameter.numel() for parameter in self.encoder.parameters() if parameter.requires_grad),
            encoder_total_parameters=sum(parameter.numel() for parameter in self.encoder.parameters()),
        )

    def pool(self, hidden: Tensor, attention_mask: Tensor | None) -> Tensor:
        if self.pooling == "first_token":
            return hidden[:, 0]
        if attention_mask is None:
            raise TechnicalExclusion(f"{self.candidate_id} mean pooling requires attention_mask")
        mask = attention_mask.unsqueeze(-1).to(dtype=hidden.dtype)
        return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)

    def encode(self, batch: Mapping[str, Tensor]) -> Tensor:
        # Remote-code encoders can expose a narrower forward contract than a
        # tokenizer (notably GTE under current Transformers).  Passing only
        # declared keyword inputs is protocol-neutral and avoids routing an
        # unsupported auxiliary tensor into the custom model.
        accepted = inspect.signature(self.encoder.forward).parameters
        kwargs = dict(batch) if any(p.kind is p.VAR_KEYWORD for p in accepted.values()) else {k:v for k,v in batch.items() if k in accepted}
        input_ids=kwargs.get("input_ids")
        try: embeddings=getattr(self.encoder, "get_input_embeddings", lambda: None)()
        except (NotImplementedError, AttributeError): embeddings=None
        if input_ids is not None and embeddings is not None:
            lo,hi=int(input_ids.min()),int(input_ids.max())
            if lo < 0 or hi >= embeddings.num_embeddings: raise TechnicalExclusion(f"{self.candidate_id} token IDs [{lo},{hi}] outside embedding table {embeddings.num_embeddings}")
        output = self.encoder(**kwargs)
        hidden = getattr(output, "last_hidden_state", None)
        if hidden is None:
            hidden = getattr(output, "last_hidden_states", None)
        if hidden is None or not isinstance(hidden, Tensor):
            raise TechnicalExclusion(f"{self.candidate_id} returned no supported hidden representation")
        return self.pool(hidden, batch.get("attention_mask"))


class ScutModel(nn.Module):
    def __init__(self, adapter: BackboneAdapter, semantic_labels: int):
        super().__init__()
        self.adapter = adapter
        # BackboneAdapter is intentionally a lightweight contract rather than
        # an nn.Module; register its encoder so model.to(device), optimizer
        # discovery, and state_dict include the actual backbone.
        self.encoder = adapter.encoder
        self.dropout = nn.Dropout(0.1)
        self.semantic = nn.Linear(adapter.hidden_size, semantic_labels)
        self.kind = nn.Linear(adapter.hidden_size, 3)
        self.action = nn.Linear(adapter.hidden_size, 1)

    def forward(self, batch: Mapping[str, Tensor]) -> tuple[Tensor, Tensor, Tensor]:
        representation = self.dropout(self.adapter.encode(batch))
        return self.semantic(representation), self.kind(representation), self.action(representation)


def build_adapter(candidate_id: str, revision: str, *, cache_dir: str | None = None) -> BackboneAdapter:
    """Load only an immutable pre-resolved revision; preflight owns resolution."""
    if candidate_id not in CANDIDATES:
        raise ValueError(f"unknown candidate: {candidate_id}")
    if not revision or len(revision) < 7:
        raise ValueError("an immutable Hub commit revision is required")
    from transformers import AutoModel, AutoTokenizer

    candidate = CANDIDATES[candidate_id]
    common = {"revision": revision, "cache_dir": cache_dir, "trust_remote_code": candidate["trust_remote_code"]}
    tokenizer = AutoTokenizer.from_pretrained(candidate["model_id"], **common)
    encoder = AutoModel.from_pretrained(candidate["model_id"], **common)
    return BackboneAdapter(candidate_id, revision, tokenizer, encoder, pooling=candidate["pooling"])
