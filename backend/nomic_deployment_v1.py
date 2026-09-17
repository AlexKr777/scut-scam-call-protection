"""Lazy local inference adapter for the frozen NOMIC_DEPLOYMENT_V1 artifact."""
from __future__ import annotations
import json
import os
from pathlib import Path
from .constants import local_root
from .hybrid_v1 import NomicSignal

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "output" / "hybrid_v1" / "NOMIC_DEPLOYMENT_V1"


def nomic_cache_dir() -> Path:
    configured = os.environ.get("SCUT_NOMIC_CACHE_DIR", "").strip()
    cache = Path(configured).expanduser().resolve() if configured else local_root() / "nomic-hf-cache"
    # Transformers remote-code modules must share the packaged cache rather
    # than silently resolving through a per-user Hugging Face default.
    for key in ("HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE", "HF_MODULES_CACHE"):
        os.environ[key] = str(cache if key != "HF_MODULES_CACHE" else cache / "modules")
    return cache

class NomicDeploymentV1:
    def __init__(self, artifact: Path = ARTIFACT):
        import torch
        from scripts.championship_backbones import build_adapter
        from .nomic_runtime_model import NonlinearScutModel
        metadata = json.loads((artifact / "metadata.json").read_text(encoding="utf-8")); checkpoint = torch.load(artifact / "model.pt", map_location="cuda", weights_only=True)
        self.labels, self.metadata = checkpoint["labels"], metadata
        self.adapter = build_adapter("nomic_v2_moe", metadata["revision"], cache_dir=str(nomic_cache_dir()))
        self.model = NonlinearScutModel(self.adapter, len(self.labels)).cuda(); self.model.load_state_dict(checkpoint["state_dict"], strict=True); self.model.eval()
    def score(self, turns: list[tuple[str, str]]) -> NomicSignal:
        import torch
        from scripts.tail_aware_encoder import pack_turns
        encoded = self.adapter.tokenizer([pack_turns(turns, self.adapter.tokenizer, 384)], padding=True, truncation=True, max_length=384, return_tensors="pt")
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16): semantic, kind, action = self.model({key: value.cuda() for key, value in encoded.items()})
        semantic_values = torch.sigmoid(semantic[0].float()).cpu().tolist(); kind_values = torch.softmax(kind[0].float(), dim=0).cpu().tolist()
        return NomicSignal(float(torch.sigmoid(action[0, 0].float()).cpu()), dict(zip(self.labels, semantic_values)), dict(zip(("dangerous", "protective", "legitimate"), kind_values)), "NOMIC_DEPLOYMENT_V1")
