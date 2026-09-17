"""Train the non-championship NOMIC_DEPLOYMENT_V1 on permitted TRAIN only."""
from __future__ import annotations
import hashlib, json, os, random, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
OUT = ROOT / "output" / "hybrid_v1" / "NOMIC_DEPLOYMENT_V1"

def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""): hasher.update(block)
    return hasher.hexdigest().upper()

def main() -> None:
    import torch
    from scripts.championship_backbones import build_adapter
    from scripts.championship_common import configure_ml_caches, load_train_records
    from scripts.run_brain_championship_v3 import NonlinearScutModel
    from scripts.tail_aware_encoder import dangerous_action_target, pack_turns
    if not torch.cuda.is_available(): raise RuntimeError("NOMIC_DEPLOYMENT_V1 requires CUDA; no CPU substitute is allowed")
    seed = 17; random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    cache_paths = configure_ml_caches(ROOT / ".local" / "ml-cache")
    rows, labels, lineage = load_train_records(ROOT)  # This loader never materializes observed validation.
    OUT.mkdir(parents=True, exist_ok=True)
    adapter = build_adapter("nomic_v2_moe", "1066b6599d099fbb93dfcb64f9c37a7c9e503e85", cache_dir=str(cache_paths["HF_HOME"]))
    model = NonlinearScutModel(adapter, len(labels)).cuda()
    kinds = {"dangerous": 0, "protective": 1, "legitimate": 2}
    pos = np.sum([[label in row["labels"] for label in labels] for row in rows], axis=0)
    semantic_loss = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(np.minimum((len(rows) - pos) / np.maximum(pos, 1), 4), device="cuda", dtype=torch.float32))
    kind_counts = np.bincount([kinds[row["kind"]] for row in rows], minlength=3)
    kind_loss = torch.nn.CrossEntropyLoss(weight=torch.tensor(np.clip(len(rows) / (3 * np.maximum(kind_counts, 1)), .5, 3), device="cuda", dtype=torch.float32))
    action_targets = np.array([dangerous_action_target(row) for row in rows])
    action_loss = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(min((len(rows)-action_targets.sum())/max(action_targets.sum(), 1), 4), device="cuda", dtype=torch.float32))
    precision = "bf16" if torch.cuda.is_bf16_supported() else "fp16"
    if precision != "bf16": raise RuntimeError("approved deployment precision requires BF16 on this RTX 5070")
    scaler = torch.amp.GradScaler("cuda", enabled=False); history = []; torch.cuda.reset_peak_memory_stats(); started = time.time()
    def collate(part):
        encoded = adapter.tokenizer([pack_turns(row["turns"], adapter.tokenizer, 384) for row in part], padding=True, truncation=True, max_length=384, return_tensors="pt")
        batch = {key: value.cuda() for key, value in encoded.items()}
        semantic = torch.tensor([[label in row["labels"] for label in labels] for row in part], device="cuda", dtype=torch.float32)
        kind = torch.tensor([kinds[row["kind"]] for row in part], device="cuda")
        action = torch.tensor([dangerous_action_target(row) for row in part], device="cuda", dtype=torch.float32)
        return batch, semantic, kind, action
    for phase, epochs in (("warmup", 1), ("finetune", 4)):
        if phase == "warmup":
            for parameter in adapter.encoder.parameters(): parameter.requires_grad_(False)
            proof = {"block_ids": []}
        else:
            configured = adapter.configure_trainable_layers(4); proof = {"block_ids": configured.block_ids, "encoder_trainable_parameters": configured.encoder_trainable_parameters}
        encoder_parameters = set(adapter.encoder.parameters())
        optimizer = torch.optim.AdamW([
            {"params": [p for p in model.parameters() if p.requires_grad and p not in encoder_parameters], "lr": 3e-4},
            {"params": [p for p in adapter.encoder.parameters() if p.requires_grad], "lr": 4e-6},
        ], weight_decay=.01)
        for epoch in range(epochs):
            model.train(); losses = []; optimizer.zero_grad()
            for index in range(0, len(rows), 8):
                batch, semantic, kind, action = collate(rows[index:index+8])
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    s, k, a = model(batch); loss = (semantic_loss(s, semantic) + .35 * kind_loss(k, kind) + .5 * action_loss(a.squeeze(-1), action)) / 2
                loss.backward(); losses.append(float(loss.detach()) * 2)
                if ((index // 8) + 1) % 2 == 0 or index + 8 >= len(rows):
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step(); optimizer.zero_grad()
            history.append({"phase": phase, "epoch": epoch + 1, "loss": sum(losses) / len(losses)})
    checkpoint = OUT / "model.pt"; torch.save({"state_dict": model.state_dict(), "labels": labels}, checkpoint)
    adapter.tokenizer.save_pretrained(OUT / "tokenizer")
    metadata = {"artifact": "NOMIC_DEPLOYMENT_V1", "NOT_CHAMPIONSHIP_CHAMPION": True, "UNSEEN_VALIDATION_NOT_YET_RUN": True, "ENGINEERING_DEPLOYMENT_SEED": seed, "metric_scope": "TRAIN_ONLY_NO_VALIDATION_LOADED", "model_id": adapter.model_id, "revision": adapter.revision, "architecture": "top_4_small_nonlinear_head", "max_tokens": 384, "precision": precision, "schedule": {"warmup_epochs": 1, "finetune_epochs": 4, "micro_batch": 8, "effective_batch": 16, "head_lr": 3e-4, "encoder_lr": 4e-6}, "train_records": len(rows), "lineage": lineage, "labels": labels, "trainable_proof": proof, "training_history": history, "duration_seconds": time.time()-started, "peak_vram_bytes": int(torch.cuda.max_memory_allocated()), "checkpoint_sha256": sha256(checkpoint)}
    (OUT / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checkpoint": str(checkpoint), "sha256": metadata["checkpoint_sha256"], "train_records": len(rows)}, ensure_ascii=False))

if __name__ == "__main__": main()
